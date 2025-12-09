from flask import Flask, render_template, request, jsonify, session, send_from_directory
import paramiko
from flask_session import Session
import os
import time
import socket
from pathlib import Path
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'clave_segura_frutiger_aero_2024'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Configurar rutas locales
BASE_DIR = Path(__file__).parent
SOURCES_DIR = BASE_DIR / 'sources'

class SSHJumpHostManager:
    def __init__(self):
        self.connections = {}
    
    def create_ssh_tunnel(self, jump_host, jump_user, jump_password, 
                          target_host, target_user, target_password):
        """
        Crea un túnel SSH usando el patrón -J (Jump Host)
        """
        try:
            # Conectar al jump host
            jump_transport = paramiko.Transport((jump_host, 22))
            jump_transport.connect(username=jump_user, password=jump_password)
            
            # Establecer canal al host destino
            dest_addr = (target_host, 22)
            local_addr = ('127.0.0.1', 0)
            
            channel = jump_transport.open_channel(
                "direct-tcpip", 
                dest_addr, 
                local_addr
            )
            
            if channel is None:
                raise Exception(f"No se pudo establecer canal al host destino: {target_host}")
            
            # Conectar al host destino a través del canal
            target_transport = paramiko.Transport(channel)
            target_transport.connect(username=target_user, password=target_password)
            
            # Crear cliente SSH
            target_ssh = paramiko.SSHClient()
            target_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            target_ssh._transport = target_transport
            
            return {
                'success': True,
                'ssh': target_ssh,
                'jump_transport': jump_transport,
                'target_transport': target_transport,
                'message': f'Conectado a {target_user}@{target_host} via {jump_user}@{jump_host}'
            }
            
        except paramiko.AuthenticationException as e:
            return {'success': False, 'message': f'Error de autenticación: {str(e)}'}
        except paramiko.SSHException as e:
            return {'success': False, 'message': f'Error SSH: {str(e)}'}
        except socket.error as e:
            return {'success': False, 'message': f'Error de socket: {str(e)}'}
        except Exception as e:
            return {'success': False, 'message': f'Error inesperado: {str(e)}'}
    
    def connect(self, connection_id, jump_host, jump_user, jump_password, 
                target_host, target_user, target_password):
        """Conectar usando túnel SSH"""
        try:
            result = self.create_ssh_tunnel(
                jump_host=jump_host,
                jump_user=jump_user,
                jump_password=jump_password,
                target_host=target_host,
                target_user=target_user,
                target_password=target_password
            )
            
            if result['success']:
                self.connections[connection_id] = {
                    'ssh': result['ssh'],
                    'jump_transport': result.get('jump_transport'),
                    'target_transport': result.get('target_transport'),
                    'jump_host': jump_host,
                    'target_host': target_host,
                    'username': target_user,
                    'connected_at': time.time()
                }
                
                # RUTA ESPECÍFICA
                project_path = "/home/rvalenzuela/tesisBailando/Bailando-main/tpami_bailandopp"
                
                # Detectar conda
                detection_commands = [
                    'which conda',
                    'ls ~/anaconda3/bin/conda 2>/dev/null || echo "No anaconda3"',
                    'ls ~/miniconda3/bin/conda 2>/dev/null || echo "No miniconda3"',
                ]
                
                full_detection = " && ".join(detection_commands)
                stdin, stdout, stderr = result['ssh'].exec_command(f'cd {project_path} && {full_detection}')
                detection_output = stdout.read().decode().strip()
                
                output = f"{result['message']}\n\n=== DETECCIÓN DE CONDA ===\n{detection_output}"
                
                return True, output
            
            return False, result['message']
            
        except Exception as e:
            return False, f"Error de conexión: {str(e)}"
    
    def get_image_lists(self):
        """Obtener lista de imágenes locales de las carpetas Top y Bot"""
        try:
            # Verificar si existen las carpetas
            top_path = SOURCES_DIR / 'Top'
            bot_path = SOURCES_DIR / 'Bot'
            
            if not top_path.exists():
                top_path.mkdir(parents=True, exist_ok=True)
            if not bot_path.exists():
                bot_path.mkdir(parents=True, exist_ok=True)
            
            # Obtener imágenes Top
            top_images = []
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.webp']:
                top_images.extend([str(p.relative_to(SOURCES_DIR)) for p in top_path.glob(ext)])
            
            # Obtener imágenes Bot
            bot_images = []
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.webp']:
                bot_images.extend([str(p.relative_to(SOURCES_DIR)) for p in bot_path.glob(ext)])
            
            # Ordenar alfabéticamente
            top_images.sort()
            bot_images.sort()
            
            return True, {
                'top_images': top_images,
                'bot_images': bot_images,
                'top_count': len(top_images),
                'bot_count': len(bot_images)
            }
            
        except Exception as e:
            return False, f"Error al obtener lista de imágenes locales: {str(e)}"
    
    def execute_command(self, connection_id, command, use_conda=True):
        """Ejecutar comando en el servidor remoto"""
        if connection_id not in self.connections:
            return False, "Conexión no encontrada"
        
        try:
            ssh = self.connections[connection_id]['ssh']
            project_path = "/home/rvalenzuela/tesisBailando/Bailando-main/tpami_bailandopp"
            
            # USAR ESTE ENFOQUE: Ejecutar conda run
            if use_conda:
                # Método 1: Usar conda run (funciona en scripts no interactivos)
                full_command = f"""
    cd "{project_path}"
    # Usar conda run para ejecutar en el entorno específico
    /home/rvalenzuela/miniconda3/bin/conda run -n pytorch3d_env --no-capture-output bash -c '{command.replace("'", "'\"'\"'")}'
    """
            else:
                full_command = f"cd {project_path} && {command}"
            
            # Ejecutar el comando
            stdin, stdout, stderr = ssh.exec_command(full_command, get_pty=True)
            
            # Leer salida
            output = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            exit_code = stdout.channel.recv_exit_status()
            
            return True, {
                'output': output,
                'error': error,
                'exit_code': exit_code,
                'command': command
            }
            
        except Exception as e:
            return False, f"Error al ejecutar comando: {str(e)}"
    
    def create_insertx_file(self, connection_id, top_index, bot_index, top_filename, bot_filename):
        """Crear archivo insertX.py en el servidor remoto"""
        if connection_id not in self.connections:
            return False, "Conexión no encontrada"
        
        try:
            ssh = self.connections[connection_id]['ssh']
            project_path = "/home/rvalenzuela/tesisBailando/Bailando-main/tpami_bailandopp"
            
            # Crear contenido del archivo insertX.py según el formato que necesitas
            x_code = f"""# insertX.py
def initialX():
    print("\\n=== VALORES X DESDE LA WEB ===")
    up_value = {top_index}
    down_value = {bot_index}
    print(f"UP sequence (índice): {{up_value}}")
    print(f"DOWN sequence (índice): {{down_value}}")
    print("=" * 30)
    return up_value, down_value
"""
            
            # Crear archivo insertX.py en el servidor remoto
            upload_command = f"""cd {project_path} && cat > insertX.py << 'EOF'
{x_code}
EOF"""
            
            stdin, stdout, stderr = ssh.exec_command(upload_command, get_pty=True)
            output = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            
            # Verificar que se creó el archivo
            verify_command = f"cd {project_path} && ls -la insertX.py && echo '=== CONTENIDO ===' && cat insertX.py"
            stdin, stdout, stderr = ssh.exec_command(verify_command, get_pty=True)
            verify_output = stdout.read().decode('utf-8', errors='ignore')
            verify_error = stderr.read().decode('utf-8', errors='ignore')
            
            if "No such file or directory" in verify_output:
                return False, "No se pudo crear insertX.py"
            
            return True, f"Archivo insertX.py creado exitosamente\n{verify_output}"
            
        except Exception as e:
            return False, f"Error al crear insertX.py: {str(e)}"
    
    def get_videos_list(self, connection_id):
        """Obtener lista de videos del servidor remoto"""
        if connection_id not in self.connections:
            return False, "Conexión no encontrada"
        
        try:
            ssh = self.connections[connection_id]['ssh']
            
            # Ruta específica de videos
            videos_path = "/home/rvalenzuela/tesisBailando/Bailando-main/tpami_bailandopp/experiments/actor_critic/eval_rotmat/videos/ep000010"
            
            # Comando para listar videos MP4 con detalles
            command = f"""
cd "{videos_path}"
echo "=== LISTANDO VIDEOS ==="
ls -la *.mp4 2>/dev/null | while read line; do
    if [ ! -z "$line" ]; then
        filename=$(echo "$line" | awk '{{print $9}}')
        size=$(echo "$line" | awk '{{print $5}}')
        modified=$(echo "$line" | awk '{{print $6" "$7" "$8}}')
        timestamp=$(date -d "$modified" +%s 2>/dev/null || echo "0")
        echo "$filename|$size|$timestamp"
    fi
done
echo "=== FIN ==="
"""
            
            stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
            output = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            
            # Parsear la salida
            videos = []
            lines = output.strip().split('\n')
            
            for line in lines:
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        videos.append({
                            'filename': parts[0],
                            'size': int(parts[1]) if parts[1].isdigit() else 0,
                            'modified': int(parts[2]) if parts[2].isdigit() else 0
                        })
            
            return True, videos
            
        except Exception as e:
            return False, f"Error al obtener videos: {str(e)}"
    
    def get_video_file(self, connection_id, filename):
        """Obtener archivo de video del servidor remoto"""
        if connection_id not in self.connections:
            return False, "Conexión no encontrada"
        
        try:
            ssh = self.connections[connection_id]['ssh']
            videos_path = "/home/rvalenzuela/tesisBailando/Bailando-main/tpami_bailandopp/experiments/actor_critic/eval_rotmat/videos/ep000010"
            full_path = f"{videos_path}/{filename}"
            
            # Verificar que el archivo existe
            command = f'[ -f "{full_path}" ] && echo "EXISTS" || echo "NOT_FOUND"'
            stdin, stdout, stderr = ssh.exec_command(command)
            exists = stdout.read().decode().strip()
            
            if exists != "EXISTS":
                return False, "Archivo no encontrado"
            
            # Obtener el archivo
            command = f'cat "{full_path}"'
            stdin, stdout, stderr = ssh.exec_command(command, bufsize=4096)
            
            # Leer el archivo en chunks
            video_data = BytesIO()
            chunk_size = 8192
            
            while True:
                chunk = stdout.read(chunk_size)
                if not chunk:
                    break
                video_data.write(chunk)
            
            video_data.seek(0)
            
            return True, video_data
            
        except Exception as e:
            return False, f"Error al obtener video: {str(e)}"
    
    def close_connection(self, connection_id):
        """Cerrar conexión SSH"""
        if connection_id in self.connections:
            try:
                conn = self.connections[connection_id]
                if conn.get('target_transport'):
                    conn['target_transport'].close()
                if conn.get('jump_transport'):
                    conn['jump_transport'].close()
                if conn.get('ssh'):
                    conn['ssh'].close()
            except:
                pass
            del self.connections[connection_id]
            return True
        return False

# Instancia global del gestor de conexiones
ssh_manager = SSHJumpHostManager()

@app.route('/')
def index():
    """Página principal"""
    connection_status = session.get('connection_status', '🔴 Desconectado')
    return render_template('index.html', 
                         connection_status=connection_status,
                         title="SSH Client - Herramienta de Soporte Creativo para la Generación de Coreografías")

@app.route('/connect', methods=['POST'])
def connect():
    """Establecer conexión SSH con túnel"""
    data = request.json
    
    required_fields = [
        'jump_host', 'jump_user', 'jump_password',
        'target_host', 'target_user', 'target_password'
    ]
    
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'success': False, 'message': f'Falta el campo: {field}'})
    
    # Generar ID único para la conexión
    connection_id = f"{data['target_user']}@{data['target_host']}_via_{data['jump_user']}_{int(time.time())}"
    
    # Intentar conexión
    success, message = ssh_manager.connect(
        connection_id=connection_id,
        jump_host=data['jump_host'],
        jump_user=data['jump_user'],
        jump_password=data['jump_password'],
        target_host=data['target_host'],
        target_user=data['target_user'],
        target_password=data['target_password']
    )
    
    if success:
        session['connection_id'] = connection_id
        session['connection_status'] = '🟢 Conectado'
        session['jump_host'] = data['jump_host']
        session['target_host'] = data['target_host']
        session['username'] = data['target_user']
        
        return jsonify({
            'success': True,
            'message': message,
            'connection_id': connection_id
        })
    else:
        session.pop('connection_id', None)
        session['connection_status'] = '🔴 Desconectado'
        return jsonify({'success': False, 'message': message})

@app.route('/get_images', methods=['GET'])
def get_images():
    """Obtener lista de imágenes locales"""
    success, result = ssh_manager.get_image_lists()
    
    if success:
        return jsonify({
            'success': True,
            'images': result
        })
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Servir imágenes locales"""
    try:
        return send_from_directory(SOURCES_DIR, filename)
    except:
        # Si no se encuentra la imagen, devolver una imagen placeholder
        return send_from_directory('static', 'placeholder.png')

@app.route('/create_insertx', methods=['POST'])
def create_insertx():
    """Crear archivo insertX.py en el servidor remoto"""
    if 'connection_id' not in session:
        return jsonify({'success': False, 'message': 'No hay conexión activa'})
    
    data = request.json
    
    top_index = data.get('top_index', -1)
    bot_index = data.get('bot_index', -1)
    top_filename = data.get('top_filename', '')
    bot_filename = data.get('bot_filename', '')
    
    if top_index == -1 or bot_index == -1:
        return jsonify({'success': False, 'message': 'Selecciona imágenes TOP y BOT'})
    
    success, result = ssh_manager.create_insertx_file(
        session['connection_id'],
        top_index,
        bot_index,
        top_filename,
        bot_filename
    )
    
    if success:
        # Extraer contenido del archivo para mostrarlo
        content_start = result.find("=== CONTENIDO ===")
        content = result[content_start:] if content_start != -1 else result
        
        return jsonify({
            'success': True,
            'message': 'insertX.py creado exitosamente',
            'content': content
        })
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/run_model', methods=['POST'])
def run_model():
    """Ejecutar el modelo actor-crítico"""
    if 'connection_id' not in session:
        return jsonify({'success': False, 'message': 'No hay conexión activa'})
    
    data = request.json
    top_index = data.get('top_index', 0)
    bot_index = data.get('bot_index', 0)
    
    # Comando para ejecutar el modelo actor-crítico
    command = f"""
echo "=== EJECUTANDO MODELO ACTOR-CRÍTICO ==="
echo "Usando índices del insertX.py: TOP={top_index}, BOT={bot_index}"
echo "========================================="
sh srun_actor_critic.sh configs/actor_critic_music_trans_400_mix_rotmat.yaml eval
"""
    
    success, result = ssh_manager.execute_command(
        session['connection_id'], 
        command,
        use_conda=True
    )
    
    if success:
        return jsonify({
            'success': True,
            'result': result
        })
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/get_videos', methods=['POST'])
def get_videos():
    """Obtener lista de videos del servidor remoto"""
    if 'connection_id' not in session:
        return jsonify({'success': False, 'message': 'No hay conexión activa'})
    
    data = request.json
    connection_id = data.get('connection_id', session.get('connection_id'))
    
    success, result = ssh_manager.get_videos_list(connection_id)
    
    if success:
        return jsonify({
            'success': True,
            'videos': result,
            'count': len(result)
        })
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/stream_video/<path:filename>')
def stream_video(filename):
    """Stream de video desde el servidor remoto"""
    if 'connection_id' not in session:
        return jsonify({'success': False, 'message': 'No hay conexión activa'}), 403
    
    success, result = ssh_manager.get_video_file(session['connection_id'], filename)
    
    if not success:
        return jsonify({'success': False, 'message': result}), 404
    
    video_data = result
    
    from flask import Response
    return Response(
        video_data,
        mimetype='video/mp4',
        headers={
            'Content-Disposition': f'inline; filename="{filename}"',
            'Content-Type': 'video/mp4'
        }
    )

@app.route('/download_video/<path:filename>')
def download_video(filename):
    """Descargar video desde el servidor remoto"""
    if 'connection_id' not in session:
        return jsonify({'success': False, 'message': 'No hay conexión activa'}), 403
    
    success, result = ssh_manager.get_video_file(session['connection_id'], filename)
    
    if not success:
        return jsonify({'success': False, 'message': result}), 404
    
    video_data = result
    
    from flask import Response
    return Response(
        video_data,
        mimetype='video/mp4',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': 'video/mp4'
        }
    )

@app.route('/execute', methods=['POST'])
def execute():
    """Ejecutar comando en el servidor remoto"""
    if 'connection_id' not in session:
        return jsonify({'success': False, 'message': 'No hay conexión activa'})
    
    data = request.json
    if 'command' not in data or not data['command']:
        return jsonify({'success': False, 'message': 'No se especificó comando'})
    
    use_conda = data.get('use_conda', False)
    
    # Ejecutar comando
    success, result = ssh_manager.execute_command(
        session['connection_id'], 
        data['command'],
        use_conda=use_conda
    )
    
    if success:
        return jsonify({
            'success': True,
            'result': result
        })
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/disconnect', methods=['POST'])
def disconnect():
    """Cerrar conexión SSH"""
    if 'connection_id' in session:
        ssh_manager.close_connection(session['connection_id'])
    
    session.pop('connection_id', None)
    session['connection_status'] = '🔴 Desconectado'
    
    return jsonify({'success': True, 'message': 'Desconectado exitosamente'})

@app.route('/status')
def status():
    """Obtener estado de la conexión"""
    connection_id = session.get('connection_id')
    connection_status = session.get('connection_status', '🔴 Desconectado')
    
    return jsonify({
        'connected': connection_id is not None,
        'status': connection_status,
        'jump_host': session.get('jump_host'),
        'target_host': session.get('target_host'),
        'username': session.get('username'),
        'connection_id': connection_id
    })

if __name__ == '__main__':
    # Asegurarse de que exista la carpeta sources
    SOURCES_DIR.mkdir(exist_ok=True)
    (SOURCES_DIR / 'Top').mkdir(exist_ok=True)
    (SOURCES_DIR / 'Bot').mkdir(exist_ok=True)
    
    print(f"📁 Directorio de imágenes: {SOURCES_DIR}")
    print(f"📸 Coloca tus imágenes en:")
    print(f"   - {SOURCES_DIR}/Top/")
    print(f"   - {SOURCES_DIR}/Bot/")
    print(f"🎥 Videos en: /home/rvalenzuela/tesisBailando/Bailando-main/tpami_bailandopp/experiments/actor_critic/eval_rotmat/videos/ep000010")
    print(f"🚀 Servidor Flask iniciando en http://localhost:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5000)