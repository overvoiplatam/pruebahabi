# Importamos las librerias basicas
from flask import Flask, Response, request
from werkzeug.exceptions import HTTPException
import json
# Importamos el archivo portable que nos permite ver el filtrado
import library.list as listAPI

# Quitar/comentar el bloque dotenv en caso de no usar archivo de configuracion .env y tener las variables de entorno asignadas de forma diferente

# dotenv/
from dotenv import load_dotenv
load_dotenv()
# /dotenv

# Iniciamos una instancia de Flask

app = Flask(__name__)

# Creamos una ruta para gestionar errores/excepciones, no es muy descriptiva,
# pero sirve para que las api clientes tengan siempre una respuesta que puedan interpretar

# Se decide que el formato de respuesta sera:
# {"success":False,"data":[],"message":"Invalid Request"}
# success: Indica si la solicitud fue correcta o incorrecta (si hubo errores procesando)
# message: Mensaje de Error/Exito
# data: Contenedor con la informacion obtenida, pude ser un diccionario vacio en caso de error

@app.errorhandler(Exception)
def handle_error(e):
    code = 500
    if isinstance(e, HTTPException):
        code = e.code
    return Response(json.dumps({"success":False,"data":{},"message":"Invalid Request"}), status=code, mimetype='application/json')


# Se crea la ruta /list como endpoint tipo POST

@app.route("/list",methods=['POST'])
def list():
    # Creamos una respuesta en caso de fallas
    result = {"success":False,"data":{}, "message":"Unknown Error"}
    result_status = 500
    # Creamos un objeto data_to_parse que contiene el body del request,
    # inicialmente lo asignamos como vacio para evitar problemas de tipo de datos

    # Para reducir las afectaciones al usuario por excepciones o errores inesperados,
    # se decide que por defecto, la API respondera siempre con informacion, y los filtros
    # utilizados serviran solo para delimitar la misma, es decir, un filtro mal configurado
    # o mal asignado se ignora en vez de cancelar la busqueda

    data_to_parse = {}

    # Intentamos hacer un parse del body que recibimos, si el contenido no es JSON, asumimos un objeto vacio,
    # pero esta parte se puede modificar para ser mas especificos en errores y mensajes al usuario
    try:
        data_to_parse=request.json
    except:
        data_to_parse = {}

    # Aqui verificamos que el objeto final data_to_parse sea un diccionario, esto nos sirve para que
    # la libreria procese unicamente este tipo de objetos, por lo que la validacion del tipo de dato recae
    # en el script que invoque la libreria
    if type(data_to_parse) == dict:
        #Aqui aplicamos ejecutamos las acciones de filtrando usando el body del cliente y en caso de error notificamos
        try:
            result["data"] = listAPI.parseBodyData(data_to_parse)
            result["success"] = True
            result_status = 200
            result["message"] = "Results Found"
        except:
            result["message"] = "Unexpected error. Check your fields and retry."
    return Response(json.dumps(result), status=result_status, mimetype='application/json')

if __name__ == '__main__':
    app.run(host= '0.0.0.0',debug=True)
