from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = 'secret123'  # Chave secreta para sessões

# Configurações do MySQL
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')

mysql = MySQL(app)

# ================= ROTAS PÚBLICAS =================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form.get('login')
        senha = request.form.get('senha')

        if not login or not senha:
            flash('Preencha todos os campos', 'danger')
            return redirect(url_for('login'))

        try:
            with mysql.connection.cursor() as cursor:  # Context manager
                cursor.execute('''
                    SELECT id, nome, tipo 
                    FROM usuarios 
                    WHERE login = %s 
                    AND senha = %s 
                    AND ativo = TRUE
                ''', (login, senha))
                
                usuario = cursor.fetchone()

                if usuario:
                    # Converter para dicionário
                    user_data = {
                        'id': usuario[0],
                        'nome': usuario[1],
                        'tipo': usuario[2].strip().upper()  # Normalização
                    }
                    
                    session.clear()
                    session.update({
                        'usuario_id': user_data['id'],
                        'usuario_nome': user_data['nome'],
                        'tipo': user_data['tipo']
                    })
                    
                    app.logger.info(f"Login type: {user_data['tipo']}")
                    
                    # Redirecionamento seguro
                    return redirect(url_for('dashboard'))
                
                flash('Credenciais inválidas', 'danger')

        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('Erro interno durante o login', 'danger')

        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        user_data = {
            'nome': request.form['nome'],
            'idade': request.form['idade'],
            'cpf': request.form['cpf'],
            'login': request.form['login'],
            'senha': request.form['senha'],
            'tipo': request.form['tipo']
        }
        
        try:
            cursor = mysql.connection.cursor()
            cursor.execute('''
                INSERT INTO usuarios (nome, idade, cpf, login, senha, tipo)
                VALUES (%(nome)s, %(idade)s, %(cpf)s, %(login)s, %(senha)s, %(tipo)s)
            ''', user_data)
            mysql.connection.commit()
            flash('Usuário cadastrado com sucesso!', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Erro ao cadastrar: {str(e)}', 'danger')
    
    return render_template('cadastro.html')

# ================= ROTAS PROTEGIDAS =================

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session or 'tipo' not in session:
        flash('Faça login para acessar esta página', 'danger')
        return redirect(url_for('login'))
    
    try:
        with mysql.connection.cursor() as cursor:  # Context manager para cursor
            if session['tipo'] == 'PROFESSOR':
                # Buscar alunos ativos
                cursor.execute('''
                    SELECT id, nome 
                    FROM usuarios 
                    WHERE tipo = "ALUNO" 
                    AND ativo = TRUE
                ''')
                alunos = cursor.fetchall()
                
                # Buscar todas as matérias
                cursor.execute('SELECT id, nome FROM materias')
                materias = cursor.fetchall()
                
                if not alunos:
                    flash('Nenhum aluno cadastrado', 'warning')
                if not materias:
                    flash('Nenhuma matéria cadastrada', 'warning')
                
                return render_template(
                    'dashboard_professor.html',
                    alunos=alunos,
                    materias=materias
                )
            
            # Dashboard para Alunos
            else:
                cursor.execute('''
                    SELECT m.nome, um.nota, um.frequencia 
                    FROM usuario_materia um
                    JOIN materias m ON um.materia_id = m.id
                    WHERE um.usuario_id = %s
                ''', (session['usuario_id'],))
                
                materias = cursor.fetchall()
                
                if not materias:
                    flash('Você não está vinculado a nenhuma matéria', 'info')
                
                return render_template(
                    'dashboard_aluno.html',
                    materias=materias
                )
    
    except Exception as e:
        mysql.connection.rollback()
        app.logger.error(f"Erro no dashboard: {str(e)}")
        flash('Erro ao carregar dashboard', 'danger')
        return redirect(url_for('index'))

@app.route('/vincular-materia', methods=['POST'])
def vincular_materia():
    if 'tipo' not in session or session['tipo'] != 'PROFESSOR':
        flash('Acesso não autorizado', 'danger')
        return redirect(url_for('login'))
    
    try:
        aluno_id = request.form.get('aluno_id')
        materia_id = request.form.get('materia_id')
        
        if not aluno_id or not materia_id:
            flash('Selecione aluno e matéria', 'danger')
            return redirect(url_for('dashboard'))
        
        with mysql.connection.cursor() as cursor:
            # Verificar se o vínculo já existe
            cursor.execute('''
                SELECT 1 
                FROM usuario_materia 
                WHERE usuario_id = %s 
                AND materia_id = %s
            ''', (aluno_id, materia_id))
            
            if cursor.fetchone():
                flash('Vínculo já existente', 'warning')
                return redirect(url_for('dashboard'))
            
            # Criar novo vínculo
            cursor.execute('''
                INSERT INTO usuario_materia 
                (usuario_id, materia_id, professor_id)
                VALUES (%s, %s, %s)
            ''', (aluno_id, materia_id, session['usuario_id']))
            
            mysql.connection.commit()
            flash('Vínculo criado com sucesso!', 'success')
    
    except ValueError:
        flash('Dados inválidos', 'danger')
    except Exception as e:
        mysql.connection.rollback()
        app.logger.error(f"Erro ao vincular: {str(e)}")
        flash(f'Erro ao vincular: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/atualizar-nota', methods=['POST'])
def atualizar_nota():
    if 'tipo' not in session or session['tipo'] != 'PROFESSOR':
        return redirect(url_for('login'))
    
    dados = {
        'aluno_id': request.form['aluno_id'],
        'materia_id': request.form['materia_id'],
        'nota': request.form['nota'],
        'frequencia': request.form['frequencia']
    }
    
    try:
        cursor = mysql.connection.cursor()
        cursor.execute('''
            UPDATE usuario_materia
            SET nota = %(nota)s, frequencia = %(frequencia)s
            WHERE usuario_id = %(aluno_id)s 
            AND materia_id = %(materia_id)s
        ''', dados)
        
        mysql.connection.commit()
        flash('Notas atualizadas com sucesso!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Erro ao atualizar: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)