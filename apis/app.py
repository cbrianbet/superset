from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, SecretStr
from sqlalchemy import create_engine, text
import random
import requests
from dotenv import load_dotenv
import os

app = FastAPI(docs_url=None, redoc_url=None)

load_dotenv()

# Replace these variables with your database connection details
DATABASE_URL = os.getenv("DATABASE_URL")
USER_RESET_TIME = 3600  # 1 hour

engine = create_engine(DATABASE_URL)


@app.get('/api2')
async def custom_swagger_ui_html():
    print(app.openapi_url)
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css",
    )

def create_original_user_roles_table():
    with engine.connect() as connection:
        create_table_query = "CREATE TABLE IF NOT EXISTS original_user_roles ( id INT, user_id INT, original_role_id INT);"
        connection.execute(create_table_query)


def update_user_role(user_id, new_role):
    with engine.connect() as connection:
        # Store the original role in the original_user_roles table
        insert_query = text(
            "INSERT INTO original_user_roles (id, user_id, original_role_id) "
            f"SELECT id, user_id, role_id FROM ab_user_role WHERE user_id={user_id}")
        connection.execute(insert_query)
        print(new_role, user_id, insert_query)

        # Delete existing user roles
        update_query = text(
            f"DELETE FROM ab_user_role Where user_id = {user_id} and role_id <> 1;")
        connection.execute(update_query)

        ur_id = random.randint(100001, 999999)

        # Update the user role in the ab_user_role table
        update_query = text(
            f"INSERT INTO ab_user_role (id, role_id, user_id) VALUES ({ur_id}, {new_role}, {user_id});")
        connection.execute(update_query)
        print(new_role, user_id, ur_id)


def reset_user_role(user_id):
    with engine.connect() as connection:
        # Retrieve the original role from the original_user_roles table
        select_query = text(
            "SELECT id, original_role_id FROM original_user_roles WHERE user_id=:user_id")
        result = connection.execute(select_query, user_id=user_id)
        original_role = result.scalar()

        # Update the user role in the ab_user_role table
        update_query = text(
            "INSERT INTO ab_user_role (id, user_id, original_role_id) VALUES(:id, :user_id, :original_role)")
        connection.execute(update_query, id=result.id,
                           user_id=user_id, original_role=original_role)


@app.on_event("startup")
async def startup_event():
    pass
    # Create the original_user_roles table on application startup
    # create_original_user_roles_table()


def get_bearer_token():
    try:
        # Replace with your Superset instance URL and credentials
        login_url = f'{os.getenv("BASE_URL")}/api/v1/security/login'
        headers = {'accept': 'application/json', 'Content-Type': 'application/json'}
        data = {
            'username': f'{os.getenv("ADMIN_USERNAME")}',
            'provider': 'db',
            'refresh': True,
            'password': f'{os.getenv("ADMIN_PASSWORD")}'
        }

        response = requests.post(login_url, headers=headers, json=data)
        if response.status_code == 200:
            token = response.json()
            return token['access_token']
        else:
            raise HTTPException(status_code=response.status_code, detail=response.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def get_csrf_token():
    try:
        # Replace with your Superset instance URL and credentials
        login_url = f'{os.getenv("BASE_URL")}/api/v1/security/csrf_token/'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {get_bearer_token()}'
        }

        response = requests.get(login_url, headers=headers)
        token = response.json()
        return token['result']
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get('/api2/update_user_role/')
async def update_user_role_endpoint(
    email: str = Query(..., title="User Email"),
    tenant_id: int = Query(..., title="Tenant ID"),
    response: Response = Response,
):
    try:
        with engine.connect() as connection:
            # Retrieve the current role for later reset
            select_query = text(f"SELECT id FROM public.ab_user WHERE email='{email}'")
            # role_query = text("SELECT id FROM ab_role WHERE name=:email")
            result = connection.execute(select_query)
            user_id = result.scalar()
            print(user_id)

            # Update the user role
            update_user_role(user_id, tenant_id)

        # Send a response with a success message and a redirect URL
        response.content = {"status": "success", "message": "Role updated successfully"}
        # Replace with your actual redirect URL
        response.headers['Location'] = 'http://localhost:8000/api2/redirect.html'
        response.status_code = 303  # 303 See Other status code for redirection

        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Serve the redirect.html file
@app.get('/api2/redirect.html', response_class=FileResponse)
async def read_redirect_html():
    return "redirect.html"


# Serve User Roles api
@app.get('/api2/roles')
async def user_roles():
    try:
        with engine.connect() as connection:
            # Retrieve roles from the 'ab_role' table
            select_query = text("SELECT * FROM public.ab_role")
            result = connection.execute(select_query)
            roles = [dict(row) for row in result]

        return {"status": "success", "roles": roles}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get('/api2/create_role/{role_name}')
async def create_role(role_name: str):
    try:
        with engine.connect() as connection:
            create_query = text("""
                INSERT INTO public.ab_role (id, name)
                VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM public.ab_role), :name)
                RETURNING id
            """)
            result = connection.execute(create_query, name=role_name)

            created_id = result.scalar()
            return {"role_id": created_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


class UserCreate(BaseModel):
    username: str
    active: bool
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    roles: list[int]


# Serve Roles api
@app.post('/api2/create/user')
async def user_create(user: UserCreate):
    try:
        url = f'{os.getenv("BASE_URL")}/api/v1/security/users/'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {get_bearer_token()}',
            'X-CSRFToken': get_csrf_token(),
        }

        response = requests.post(url, headers=headers, json=user.__dict__)

        if response.status_code in [200, 201, 202]:
            return {"status": "success", "response": response.json()}
        else:
            raise HTTPException(status_code=response.status_code, detail=response.json())

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


class DbCreate(BaseModel):
    allow_ctas: Optional[bool] = False
    allow_cvas: Optional[bool] = False
    allow_dml: Optional[bool] = False
    allow_file_upload: Optional[bool] = False
    allow_run_async: Optional[bool] = False
    cache_timeout: Optional[int] = 0
    database_name: str
    driver: str
    engine: str
    expose_in_sqllab: Optional[bool] = True
    external_url: Optional[str] = None
    force_ctas_schema: Optional[str] = None
    impersonate_user: Optional[bool] = False
    is_managed_externally: Optional[bool] = False
    server_cert: Optional[str] = None
    sqlalchemy_uri: str


# Serve Roles api
@app.post('/api2/create/database')
async def create_database(db: DbCreate):
    try:
        db_url = f'{os.getenv("BASE_URL")}/api/v1/database/'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {get_bearer_token()}'
        }

        # Use the auth token for subsequent API calls

        response = requests.post(db_url, headers=headers, json=db.__dict__)

        if response.status_code in [200, 201, 202]:
            return {"status": "success", "response": response.json()}
        else:
            raise HTTPException(status_code=response.status_code, detail=response.json())

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
