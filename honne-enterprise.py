import streamlit as st
import tools
import json
import os
from datetime import datetime
import boto3
import hmac
import base64
import hashlib
import pandas as pd
from botocore.exceptions import ClientError
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de AWS Cognito
USER_POOL_ID = 'us-east-1_DzVB7yQ87'
CLIENT_ID = 'm47hdqpevjk6hv6m7ul9jqonv'
CLIENT_SECRET = '18i75h8ho88rrkq2gnkg1f6amdm09ilt6g137iot4b897ttqa8ps'
REGION_NAME = 'us-east-1'

# Funciones auxiliares

def create_user(email, temporary_password, nickname):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    try:
        response = client.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'nickname', 'Value': nickname},
                {'Name': 'custom:is_admin', 'Value': 'true' if is_admin else 'false'}
            ],
            TemporaryPassword=temporary_password,
            MessageAction='SUPPRESS'
        )
        return True, "User created successfully"
    except Exception as e:
        return False, str(e)

def update_user(username, attributes):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    try:
        response = client.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=username,
            UserAttributes=attributes
        )
        return True, "User updated successfully"
    except Exception as e:
        return False, str(e)

def delete_user(username):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    try:
        response = client.admin_delete_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        return True, "User deleted successfully"
    except Exception as e:
        return False, str(e)
    
def save_conversation(messages, filename):
    with open(filename, 'w') as f:
        json.dump(messages, f)

def load_conversation(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return []

def generate_new_filename():
    return f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

def start_new_conversation():
    st.session_state.messages = []
    st.session_state.current_conversation = "New conversation"
    st.session_state.conversation_filename = generate_new_filename()

def get_secret_hash(username):
    msg = username + CLIENT_ID
    dig = hmac.new(str(CLIENT_SECRET).encode('utf-8'), 
        msg=str(msg).encode('utf-8'), digestmod=hashlib.sha256).digest()
    d2 = base64.b64encode(dig).decode()
    return d2

def complete_new_password_challenge(email, new_password, session, nickname):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    secret_hash = get_secret_hash(email)
    try:
        response = client.respond_to_auth_challenge(
            ClientId=CLIENT_ID,
            ChallengeName='NEW_PASSWORD_REQUIRED',
            Session=session,
            ChallengeResponses={
                'USERNAME': email,
                'NEW_PASSWORD': new_password,
                'SECRET_HASH': secret_hash,
                'userAttributes.nickname': nickname,
            }
        )
        st.session_state.authenticated = True
        st.session_state.token = response['AuthenticationResult']['IdToken']
        st.session_state.awaiting_new_password = False
        return True, "Password updated and logged in successfully!"
    except Exception as e:
        return False, f"An error occurred: {str(e)}"

def login_page():

    st.markdown("<h1 style='text-align: center;'> BIENVENIDO</h1>", unsafe_allow_html=True)
    
    st.markdown("""
    <style>
        .stTextInput > div > div > input {
            width: 100%;
        }
        .stButton > button {
            width: 100%;
        }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        email = st.text_input("**Email :**", placeholder="ejemplo@dominio.com", key="email_input")
        # email = st.text_input(label="<strong>Email :</strong>",placeholder="ejemplo@dominio.com")
        password = st.text_input("**Password :**",placeholder="********", type="password")
    
        if st.button("Login"):
            success, message = login(email, password)
            if success:
                st.success(message)
                st.session_state.authenticated = True
                st.session_state.email = email
                st.rerun() 
            else:
                st.error(message)
   
def new_password_page():
    st.title("Set New Password")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    nickname = st.text_input("Nickname")

    if st.button("Submit"):
        if new_password != confirm_password:
            st.error("Passwords do not match")
        else:
            success, message = complete_new_password_challenge(st.session_state.email, new_password, st.session_state.session, nickname)
            if success:
                st.success(message)
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error(message)

def process_llm_response(user_input, show_references):
    
    if show_references:
        llm_response = tools.answer_query(user_input)
        formatted_answer = tools.format_answer(llm_response)
        return formatted_answer
    else:
        llm_response = tools.answer_query_old(user_input)
        # Asumiendo que llm_response es un diccionario con claves 'answer' y 'references'
        
        return llm_response

def logout():
    st.session_state.authenticated = False
    st.session_state.email = None
    st.session_state.token = None
    st.session_state.user_name = None  # Limpiar el nombre de usuario al cerrar sesión
    st.session_state.awaiting_new_password = False
    st.session_state.clear()
    st.rerun()
        
def chatbot_page():
    user_name = st.session_state.get('user_name', 'Usuario')
    
    st.markdown(f"<h1 style='text-align: center;'>¡Bienvenido, {user_name}! 👋</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>🤖 Honne IA 3.0 Pinecone</h2>", unsafe_allow_html=True)

    user_folder = f"conversations/{st.session_state.email.split('@')[0]}"
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)

    saved_conversations = [f for f in os.listdir(user_folder) if f.endswith('.json')]

    if st.sidebar.button("Start New Conversation"):
        start_new_conversation()

    selected_conversation = st.sidebar.selectbox(
        "Load or start a conversation",
        ["New conversation"] + saved_conversations,
        key="conversation_selector"
    )
    
    show_references = st.sidebar.checkbox("Show References", value=True, key="show_references")

    if selected_conversation == "New conversation":
        if "messages" not in st.session_state or st.session_state.current_conversation != "New conversation":
            start_new_conversation()
    else:
        if "current_conversation" not in st.session_state or st.session_state.current_conversation != selected_conversation:
            st.session_state.messages = load_conversation(os.path.join(user_folder, selected_conversation))
            st.session_state.current_conversation = selected_conversation
            st.session_state.conversation_filename = selected_conversation

    if "messages" in st.session_state:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

    user_input = st.chat_input("Type your message here")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        assistant_response = process_llm_response(user_input, show_references)
        st.session_state.messages.append({"role": "assistant", "content": assistant_response})

        save_conversation(st.session_state.messages, os.path.join(user_folder, st.session_state.conversation_filename))
        
        st.rerun()
        
    if st.sidebar.button("Logout", key="logout-button",use_container_width=True):
        logout()
        
def list_users():
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    response = client.list_users(UserPoolId=USER_POOL_ID)
    return response['Users']

def delete_user(username_or_email):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    try:
        # Primero, intentamos encontrar al usuario por correo electrónico
        response = client.list_users(
            UserPoolId=USER_POOL_ID,
            Filter=f'email = "{username_or_email}"'
        )
        
        if response['Users']:
            username = response['Users'][0]['Username']
        else:
            # Si no se encuentra por correo, asumimos que es un nombre de usuario
            username = username_or_email
        
        response = client.admin_delete_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        return True, f"User {username_or_email} deleted successfully"
    except Exception as e:
        return False, str(e)

def admin_page():
    st.title("Admin Dashboard")

    admin_function = st.selectbox(
        "Choose Admin Function",
        ["Show Users", "Create User", "Update User", "Delete User", "View All Conversations"]
    )

    if admin_function == "Show Users":
        show_users()
    elif admin_function == "Create User":
        create_user_form()
    elif admin_function == "Update User":
        update_user_form()
    elif admin_function == "Delete User":
        delete_user_form()
    elif admin_function == "View All Conversations":
        view_all_conversations()
        
    if st.sidebar.button("Logout", key="logout-button-2",use_container_width=True):
        logout()

def view_all_conversations():
    st.header("All User Conversations")
    conversations = list_all_conversations()
    
    # Crear una lista de todas las conversaciones con formato "usuario: conversación"
    all_conversations = ["Select a conversation"] + [f"{user}: {conv}" for user, user_conversations in conversations.items() for conv in user_conversations]
    
    # Usar un selectbox para mostrar todas las conversaciones
    selected_conversation = st.selectbox("Select a conversation to view", all_conversations)
    
    if selected_conversation != "Select a conversation":
        # Separar el usuario y la conversación seleccionada
        user, conversation = selected_conversation.split(": ")
        view_conversation(user, conversation)
    else:
        st.write("Please select a conversation to view its contents.")
        
        # Mostrar un resumen de las conversaciones disponibles
        st.subheader("Available Conversations:")
        for user, user_conversations in conversations.items():
            st.write(f"**{user}**: {len(user_conversations)} conversation(s)")

def view_conversation(user, conversation):
    filepath = os.path.join("conversations", user, conversation)
    with open(filepath, 'r') as f:
        messages = json.load(f)
    st.subheader(f"Conversation: {conversation}")
    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

def list_all_conversations():
    conversations = {}
    conversations_dir = "conversations"
    
    # Recorrer el directorio de conversaciones
    for user in os.listdir(conversations_dir):
        user_dir = os.path.join(conversations_dir, user)
        if os.path.isdir(user_dir):
            conversations[user] = []
            # Listar todas las conversaciones del usuario
            for conversation in os.listdir(user_dir):
                if conversation.endswith('.json'):  # Asumimos que las conversaciones se guardan como archivos JSON
                    conversations[user].append(conversation)
    
    return conversations
            
def update_user_form():
    st.header("Update User")
    update_username = st.text_input("Username to update")
    update_nickname = st.text_input("New Nickname")
    is_admin = st.checkbox("Is Admin")
    if st.button("Update User"):
        attributes = [
            {'Name': 'nickname', 'Value': update_nickname},
            {'Name': 'custom:is_admin', 'Value': 'true' if is_admin else 'false'}
        ]
        success, message = update_user(update_username, attributes)
        if success:
            st.success(message)
        else:
            st.error(message)

def show_users():
    st.header("User List")
    users = list_users()
    
    # Crear una lista de diccionarios con los datos de los usuarios
    user_data = []
    for user in users:
        user_dict = {
            'Username': user['Username'],
            'Email': next((attr['Value'] for attr in user['Attributes'] if attr['Name'] == 'email'), 'N/A'),
            'Nickname': next((attr['Value'] for attr in user['Attributes'] if attr['Name'] == 'nickname'), 'N/A'),
            'Status': user['UserStatus'],
            'Admin': any(attr['Name'] == 'custom:is_admin' and attr['Value'].lower() in ['true', '1'] for attr in user['Attributes'])
        }
        user_data.append(user_dict)
    
    # Crear el DataFrame
    df = pd.DataFrame(user_data)
    
    # Mostrar el DataFrame en Streamlit
    st.dataframe(df,use_container_width=True)
    
    # Opcionalmente, puedes agregar más visualizaciones o estadísticas
    st.write(f"Total users: {len(df)}")
    st.write(f"Admins: {df['Admin'].sum()}")
    
    # # Puedes agregar gráficos si lo deseas
    # st.bar_chart(df['Status'].value_counts())
    
def delete_user_form():
    st.header("Delete User")
    delete_option = st.radio("Delete by", ("Username", "Email"))
    if delete_option == "Username":
        delete_identifier = st.text_input("Username to delete")
    else:
        delete_identifier = st.text_input("Email to delete")
    if st.button("Delete User"):
        success, message = delete_user(delete_identifier, by_email=(delete_option == "Email"))
        if success:
            st.success(message)
        else:
            st.error(message)

def create_user_form():
    st.header("Create New User")
    
    # Obtener entradas del formulario
    new_email = st.text_input("Email")
    new_nickname = st.text_input("Nickname")
    is_admin = st.checkbox("Is Admin")
    
    # Checkbox para enviar invitación por email
    send_invitation = st.checkbox("Send Invitation by Email")

    # Condicional para mostrar la opción de generar una contraseña temporal
    if not send_invitation:
        generate_password = st.checkbox("Generate Temporary Password")
    else:
        generate_password = False

    # Capturar la contraseña temporal solo si no se selecciona 'send_invitation'
    temporary_password = ""
    if not send_invitation and not generate_password:
        temporary_password = st.text_input("Temporary Password", type="password")

    # Botón para crear el usuario
    if st.button("Create User"):
        success, message = create_user(new_email, new_nickname, is_admin, send_invitation, generate_password, temporary_password)
        if success:
            st.success(message)
        else:
            st.error(message)

def create_user(email, nickname, is_admin=False, send_invitation=False, generate_password=False, temporary_password=""):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    try:
        user_attributes = [
            {'Name': 'email', 'Value': email},
            {'Name': 'email_verified', 'Value': 'true'},
            {'Name': 'nickname', 'Value': nickname},
            {'Name': 'custom:is_admin', 'Value': 'true' if is_admin else 'false'}
        ]
        
        # Construcción del diccionario de parámetros
        params = {
            'UserPoolId': USER_POOL_ID,
            'Username': email,
            'UserAttributes': user_attributes
        }

        if not send_invitation:
            if generate_password:
                response = client.admin_create_user(**params)
                # Se genera una contraseña temporal automática
                st.write("Cognito generará una contraseña temporal y la enviará al usuario.")
            else:
                # Si el usuario proporciona una contraseña temporal
                if temporary_password:
                    params['TemporaryPassword'] = temporary_password
                else:
                    return False, "Temporary Password is required if not sending an invitation."
        
        if send_invitation:
            # Enviar invitación por correo electrónico
            params['DesiredDeliveryMediums'] = ['EMAIL']
            response = client.admin_create_user(**params)

        return True, "User created successfully"
    except Exception as e:
        return False, str(e)
    
def delete_user(identifier, by_email=False):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    try:
        if by_email:
            # Primero, busca el usuario por email
            response = client.list_users(
                UserPoolId=USER_POOL_ID,
                Filter=f'email = "{identifier}"'
            )
            if not response['Users']:
                return False, "User not found"
            username = response['Users'][0]['Username']
        else:
            username = identifier
        
        response = client.admin_delete_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        return True, "User deleted successfully"
    except Exception as e:
        return False, str(e)
    
def show_session_state():
    st.sidebar.header("Session State (Debug)")
    for key, value in st.session_state.items():
        st.sidebar.text(f"{key}: {value}")

def login(email, password):
    client = boto3.client('cognito-idp', region_name=REGION_NAME)
    secret_hash = get_secret_hash(email)
    try:
        response = client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': email,
                'PASSWORD': password,
                'SECRET_HASH': secret_hash
            }
        )

        if 'ChallengeName' in response and response['ChallengeName'] == 'NEW_PASSWORD_REQUIRED':
            st.session_state.session = response['Session']
            st.session_state.awaiting_new_password = True
            st.session_state.email = email
            st.session_state.user_attributes = json.loads(response['ChallengeParameters']['userAttributes'])
            st.rerun()
        
        st.session_state.authenticated = True
        st.session_state.token = response['AuthenticationResult']['IdToken']
        st.session_state.awaiting_new_password = False
        
        # Get user info and check if admin
        user_info = client.get_user(AccessToken=response['AuthenticationResult']['AccessToken'])
        st.session_state.user_name = "Usuario"
        st.session_state.is_admin = False
        # print (user_info['UserAttributes'])
        for attribute in user_info['UserAttributes']:
            if attribute['Name'] == 'name':
                st.session_state.user_name = attribute['Value']
            elif attribute['Name'] == 'email':
                st.session_state.user_name = attribute['Value'].split('@')[0]
            elif attribute['Name'] == 'custom:is_admin':
                # Check for both string and int representations
                st.session_state.is_admin = attribute['Value'].lower() in ['true', '1']
        
        # print(f"Login successful. Is admin: {st.session_state.is_admin}")  # Debug print
        return True, "Login successful"
    
    except Exception as e:
        print(f"Error during login: {str(e)}")
        return False, f"An unexpected error occurred: {str(e)}"

def init_session_state():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'awaiting_new_password' not in st.session_state:
        st.session_state.awaiting_new_password = False
    if 'email' not in st.session_state:
        st.session_state.email = None
    if 'page' not in st.session_state:
        st.session_state.page = "Landing"
    if 'selected_product' not in st.session_state:
        st.session_state.selected_product = None

def landing_page():
    # st.title("Bienvenido a Honne Services")
    
    # # Mostrar el logo de la empresa
    # st.image("Logo-honne.png", width=200)
    st.markdown("""
    <style>
    .center {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
    }
    </style>
    <div class="center">
        <img src="https://honneservices.com/wp-content/uploads/2024/05/LOGO-CABECERA-color-2.png" width="200" />
        <h1>Bienvenido a Honne Services</h1>
        
    </div>
    """, unsafe_allow_html=True)
    st.markdown(' ')
    
    st.write("""
        En **Honne Services**, nos especializamos en potenciar la eficiencia y el crecimiento empresarial mediante soluciones tecnológicas avanzadas. 
        Nuestras soluciones están diseñadas para automatizar procesos, optimizar operaciones y reducir costos, lo que permite a las empresas maximizar su 
        productividad y rentabilidad.

        Con una sólida presencia en México, EE.UU., Colombia, Chile y Francia, hemos establecido una sólida reputación al promover la innovación y 
        facilitar la adopción de tecnologías emergentes como IoT, Blockchain e Inteligencia Artificial. Estas tecnologías no solo optimizan la eficiencia 
        operativa, sino que también generan nuevas oportunidades de negocio, ayudando a las empresas a mantenerse a la vanguardia en sus respectivas industrias.
    """)

    st.markdown("""
        Descubre más sobre nuestros servicios visitando [nuestro sitio web](https://honneservices.com/). Estamos aquí para ayudarte a alcanzar 
        el éxito con soluciones personalizadas que se ajusten a tus necesidades.
    """)
    if st.sidebar.button("Logout", key="logout-button-4",use_container_width=True):
        logout()
        
def products_page():
    # Inicializa el estado de sesión si no está definido
    if 'product_selection_visible' not in st.session_state:
        st.session_state.product_selection_visible = True
    if 'selected_product' not in st.session_state:
        st.session_state.selected_product = "Selecciona un producto"
    
    if st.session_state.product_selection_visible:
        
        
        st.markdown("""
    <style>
    .center {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
    }
    </style>
    <div class="center">
        <img src="https://honneservices.com/wp-content/uploads/2024/05/LOGO-CABECERA-color-2.png" width="200" />
        <h1>Productos de Honne Services basados en IA</h1>
        
    </div>
    """, unsafe_allow_html=True)
        
        product_options = ["Selecciona un producto", "AI Chatbot", "Analytics Dashboard", "Predictive Modeling"]
        
        # Asegurarse de que siempre haya un valor válido en `selected_product`
        if st.session_state.selected_product is None:
            st.session_state.selected_product = "Selecciona un producto"
        
        # Selecciona el producto basado en el estado
        selected_product = st.selectbox(
            "Elige un producto: :arrow_down:",
            product_options,
            index=product_options.index(st.session_state.selected_product) if st.session_state.selected_product in product_options else 0,
            key="product_selector"
        )
        
        if selected_product != "Selecciona un producto":
            st.session_state.selected_product = selected_product
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Ocultar la selección de productos",use_container_width=True):
                st.session_state.product_selection_visible = False
                st.rerun()
        with col2:
            if st.button("Limpiar selección",use_container_width=True):
                # Reiniciar el valor del producto seleccionado
                st.session_state.selected_product = "Selecciona un producto"
                st.rerun()

    else:
        if st.button("Mostrar la selección de productos",use_container_width=True):
            st.session_state.product_selection_visible = True
            st.rerun()
    
    # Solo mostramos el producto si se ha seleccionado uno válido
    if st.session_state.selected_product != "Selecciona un producto":
        display_product(st.session_state.selected_product)
    elif not st.session_state.product_selection_visible:
        st.write("No ha seleccionado ningún producto. Haga clic en 'Mostrar selección de productos' para comenzar.")
    if st.sidebar.button("Logout", key="logout-button-5",use_container_width=True):
        logout()

def display_product(product):
    # st.title(product)
    
    if product == "AI Chatbot":
        chatbot_page()
    elif product == "Analytics Dashboard":
        st.write("Here you would see an interactive analytics dashboard.")
        # Add placeholder for analytics dashboard
    elif product == "Predictive Modeling":
        st.write("Access our advanced predictive modeling tools here.")
        # Add placeholder for predictive modeling tools
    
def main():
    init_session_state()

    if not st.session_state.authenticated:
        if st.session_state.awaiting_new_password:
            new_password_page()
        else:
            login_page()
    else:
        # Definir las páginas disponibles
        pages = ["Landing", "Products", "Admin"] if st.session_state.get('is_admin', False) else ["Landing", "Products"]
        
        # Usar st.selectbox en la barra lateral para la navegación
        st.sidebar.title("Navigation")
        st.session_state.page = st.sidebar.selectbox("**Selecciona una pagina** :arrow_down: ", pages)
        
        # Renderizar la página seleccionada
        if st.session_state.page == "Landing":
            landing_page()
        elif st.session_state.page == "Products":
            products_page()
        elif st.session_state.page == "Admin":
            if st.session_state.get('is_admin', False):
                admin_page()
            else:
                st.error("You don't have permission to access the admin page.")
                landing_page()  
      
if __name__ == "__main__":
    main()