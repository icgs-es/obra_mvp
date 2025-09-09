import os
import sys
import django

# Configurar Django - RUTA CORRECTA
sys.path.append('/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

def crear_usuarios_desde_excel():
    print("Iniciando creación de usuarios...")
    
    # Datos de usuarios desde tu Excel
    usuarios_data = [
        {
            'username': 'Ivan',
            'email': 'informatico@grupointasa.es',
            'password': '123456',
            'first_name': 'Ivan',
            'last_name': 'Gonzalez Sagrera',
            'phone': '610934471',
            'is_staff': True,
            'is_superuser': True
        },
        {
            'username': 'Jaime',
            'email': 'expansion@grupointasa.es',
            'password': '123456',
            'first_name': 'Jaime',
            'last_name': 'Losada',
            'is_staff': True,
            'is_superuser': False
        },
        {
            'username': 'Aurora',
            'email': 'aurora@grupointasa.es',
            'password': '123456',
            'first_name': 'Aurora',
            'last_name': 'Madrueño',
            'is_staff': True,
            'is_superuser': False
        },
        {
            'username': 'Isabel',
            'email': 'i.mendez@arqproyect.com',
            'password': '123456',
            'first_name': 'Isabel',
            'last_name': 'Mendez',
            'is_staff': True,
            'is_superuser': False
        },
        {
            'username': 'Oscar',
            'email': 'oscar@grupointasa.es',
            'password': '123456',
            'first_name': 'Oscar',
            'last_name': 'Calzada Castaño',
            'is_staff': True,
            'is_superuser': False
        }
    ]
    
    # Crear grupos/roles si no existen
    grupos = ['Administrador', 'Gerencia', 'Comercializadora', 'Constructora', 'Promotora']
    for grupo_nombre in grupos:
        Group.objects.get_or_create(name=grupo_nombre)
        print(f"✓ Grupo '{grupo_nombre}' verificado")
    
    # Crear usuarios
    for usuario_data in usuarios_data:
        username = usuario_data['username']
        
        # Verificar si el usuario ya existe
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(
                username=usuario_data['username'],
                email=usuario_data['email'],
                password=usuario_data['password'],
                first_name=usuario_data['first_name'],
                last_name=usuario_data['last_name'],
                is_staff=usuario_data.get('is_staff', False),
                is_superuser=usuario_data.get('is_superuser', False)
            )
            
            # Añadir teléfono si existe
            if 'phone' in usuario_data:
                user.phone = usuario_data['phone']
                user.save()
            
            # Asignar grupos según el rol
            if username == 'Ivan':
                grupo = Group.objects.get(name='Administrador')
                user.groups.add(grupo)
                print(f"✓ Usuario {username} creado como Administrador")
            elif username == 'Jaime':
                grupo = Group.objects.get(name='Gerencia')
                user.groups.add(grupo)
                print(f"✓ Usuario {username} creado como Gerencia")
            elif username in ['Aurora', 'Oscar']:
                grupo = Group.objects.get(name='Comercializadora')
                user.groups.add(grupo)
                print(f"✓ Usuario {username} creado como Comercializadora")
            elif username == 'Isabel':
                grupo = Group.objects.get(name='Constructora')
                user.groups.add(grupo)
                print(f"✓ Usuario {username} creado como Constructora")
                
        else:
            print(f"→ Usuario {username} ya existe")
    
    print("\n✅ Proceso de creación de usuarios completado!")
    print("\nCredenciales disponibles:")
    print("Administrador: Ivan / 123456")
    print("Gerencia: Jaime / 123456")
    print("Comercial: Aurora / 123456")
    print("Constructora: Isabel / 123456")
    print("Promotora: Oscar / 123456")

if __name__ == "__main__":
    crear_usuarios_desde_excel()