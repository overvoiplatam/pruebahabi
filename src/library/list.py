import json
import os
import mysql.connector

# Definimos los campos para los filtros

baseFieldsDefinitions = {
    "id":{
        "realField":"a.id",
        "type":"number"
    },
    "address":{
        "realField":"a.address",
        "type":"text"
    },
    "city":{
        "realField":"a.city",
        "type":"text"
    },
    "price":{
        "realField":"a.price",
        "type":"number"
    },
    "description":{
        "realField":"a.description",
        "type":"text"
    },
    "year":{
        "realField":"a.year",
        "type":"number"
    },
    "status":{
        "realField":"d.name",
        "type":"text_exact"
    }
}

# Definimos los posibles tipos de filtros a usar

baseFieldsValidations = {
    "number":["equal","sign","rank","in"],
    "text_exact":["equal","in"],
    "text":["equal","partial","in"]
}

# Para los anteriores se usa un entorno de diccionario para una ejecucion mas rapida

# Definimos nuestra Query inicial tomando como base nuestras investigaciones,
# llenaremos despues los %s con el resto de las consultas
baseSQLQuery = """
SELECT %s
    FROM
        property AS a
        LEFT JOIN
            `status_history` AS c
                ON
                    c.property_id=a.id
                AND
                    c.update_date=(
                        SELECT MAX(update_date)
                            FROM
                                status_history
                            WHERE
                                property_id=a.id
                    )
        LEFT JOIN
            `status` AS d
                ON
                    d.id=c.status_id
    WHERE
        d.name in  ('pre_venta', 'en_venta', 'vendido')
        %s
        %s
        %s
;"""

# Como buena practica, iniciaremos y finalizaremos las conexiones Mysql con cada solicitud, esto para evitar exceso de conexiones abiertas

def mysql_connection():
    mydb = mysql.connector.connect(
      host=os.getenv('DB_HOST'),
      user=os.getenv('DB_USER'),
      password=os.getenv('DB_PWD'),
      port=os.getenv('DB_PORT'),
      database=os.getenv('DB_NAME')
    )
    return {
        "connection":mydb,
        "cursor":mydb.cursor()
    }

def finish_mysql_connection(connection_object):
    connection_object["cursor"].close()
    connection_object["connection"].close()

# Esta funcion es para simplificar el reemplazo de los valores dentro del comando SQL final

def addSQLQuotes(v,p):
    if type(v) == int or type(v) == float:
        return str(v)
    return '"%s"' % p(v).decode("utf-8")

# Funcion principal

def parseBodyData(data={}):
    # Iniciamos la conexion mysql
    connection = mysql_connection()
    # Asignamos los valores a utilizar del principio
    limitPair = []
    limitFields = ""
    selectFields = ""
    filterFields = ""
    orderFields = ""
    # Si el campo fields es enviado, validamos que los campos enviados coincidan con los que tenemos en nuestro modelo de datos
    if "fields" in data and isinstance(data["fields"], list) and len(data["fields"])>0:
        for f in range(len(data["fields"])):
            if isinstance(data["fields"][f], str) and  str(data["fields"][f]) in baseFieldsDefinitions:
                selectFields+=("" if selectFields=="" else ", ") + baseFieldsDefinitions[data["fields"][f]]["realField"] + " AS `" + data["fields"][f] + "`"
    # Si no fue posible delmitar campos, seleccionamos todo
    if selectFields == "":
        selectFields = "a.* , d.name as `status`"

    # Aqui aplicamos los filtros, esta parte puede pasarse a una funcion en caso de ser demasiado compleja
    if "filters" in data and isinstance(data["filters"], list) and len(data["filters"])>0:
        for f in range(len(data["filters"])):
            if type(data["filters"][f]) is dict and 'field' in data["filters"][f] and isinstance(data["filters"][f]['field'], str):
                if  str(data["filters"][f]['field']) in baseFieldsDefinitions  and isinstance(data["filters"][f]['type'], str):
                    if "value" in data["filters"][f] and data["filters"][f]['type'] in baseFieldsValidations[baseFieldsDefinitions[data["filters"][f]['field']]["type"]]:
                        # Aqui separe el bloque if en 3 para hacerlo mas legible, pero se puede reducir un poco uniendo estos dos renglones al rededor de este comentario
                        # A continuacion se generan los filtros y se escapan usando la funcion de C escape_string
                        if isinstance(data["filters"][f]['value'], str) and data["filters"][f]['type']=="partial" and len(data["filters"][f]['value'])>0:
                            filterFields+=" AND " + baseFieldsDefinitions[data["filters"][f]['field']]["realField"] + (' LIKE %s ' % ("'%" + connection["connection"]._cmysql.escape_string(data["filters"][f]['value']).decode("utf-8") + "%'" ))
                        elif data["filters"][f]['type']=="equal" and len(str(data["filters"][f]['value']))>0:
                            if type(data["filters"][f]['value']) == int or type(data["filters"][f]['value']) == float:
                                filterFields+=" AND " + baseFieldsDefinitions[data["filters"][f]['field']]["realField"] + (' = %s ' % str(data["filters"][f]['value']))
                            elif type(data["filters"][f]['value']) == str:
                                filterFields+=" AND " + baseFieldsDefinitions[data["filters"][f]['field']]["realField"] + (' = "%s" ' % connection["connection"]._cmysql.escape_string(data["filters"][f]['value']).decode("utf-8"))
                        elif type(data["filters"][f]['value']) == list and len(data["filters"][f]['value'])>0:
                            if len(data["filters"][f]['value'])==2 and data["filters"][f]['type']=="rank":
                                if ( type(data["filters"][f]['value'][0]) == int or type(data["filters"][f]['value'][0]) == float) and ( type(data["filters"][f]['value'][1]) == int or type(data["filters"][f]['value'][1]) == float):
                                    filterFields+=" AND " + baseFieldsDefinitions[data["filters"][f]['field']]["realField"] + (' >= %s ' % str(data["filters"][f]['value'][0]))
                                    filterFields+=" AND " + baseFieldsDefinitions[data["filters"][f]['field']]["realField"] + (' <= %s ' % str(data["filters"][f]['value'][1]))
                            elif data["filters"][f]['type']=="in":
                                curedValues = [addSQLQuotes(v,connection["connection"]._cmysql.escape_string) for v in data["filters"][f]['value'] if ( type(v) == int or type(v) == float or type(v) == str and len(str(v))>0)]
                                if len(curedValues)>0:
                                    filterFields+=" AND " + baseFieldsDefinitions[data["filters"][f]['field']]["realField"] + (' IN (%s) ' % ",".join(curedValues))
                        elif data["filters"][f]['type']=="sign" and "sign" in data["filters"][f] and data["filters"][f]["sign"] in ["=","<","<=",">",">="]:
                            if type(data["filters"][f]["value"]) == int or type(data["filters"][f]["value"]) == float or type(data["filters"][f]["value"]) == str:
                                if  len(str(data["filters"][f]["value"]))>0:
                                    filterFields+=" AND " + baseFieldsDefinitions[data["filters"][f]['field']]["realField"] + (' %s %s ' % (data["filters"][f]["sign"],addSQLQuotes(data["filters"][f]["value"],connection["connection"]._cmysql.escape_string)) )
    # Aqui validamos el orden a mostrar los campos
    if 'order' in data and isinstance(data["order"], list) and len(data["order"])>0:
        for o in range(len(data["order"])):
            if type(data["order"][o]) is dict and 'field' in data["order"][o] and "direction" in data["order"][o]:
                if isinstance(data["order"][o]['field'], str) and str(data["order"][o]['field']) in baseFieldsDefinitions:
                    if type(data["order"][o]["direction"]) is str and  data["order"][o]["direction"].lower() in ["asc","desc"]:
                        orderFields+=(" ORDER BY " if orderFields=="" else " , ") + (" %s %s" % (baseFieldsDefinitions[data["order"][o]['field']]["realField"],data["order"][o]['direction']))
    # Aqui validamos la paginacion
    if "length" in data and type(data["length"]) == int and data["length"]>0:
        if "start" in data and type(data["start"]) == int and data["start"]>0:
            limitPair.append(data["start"])
        limitPair.append(data["length"])
    if len(limitPair)>0:
        limitFields = " LIMIT %s" % ",".join(str(v) for v in limitPair)
    # Contruimos la query para contar los resultados (sin limit)
    countQuery = baseSQLQuery % (" COUNT(a.id) AS Total ",filterFields,"","")
    # Contruimos la query para mostrar los resultados
    resultQuery = baseSQLQuery % (selectFields,filterFields,orderFields,limitFields)
    #Ejecutamos los Query y los almacenamos en sus variables
    connection["cursor"].execute(countQuery)
    countResult = connection["cursor"].fetchall()
    connection["cursor"].execute(resultQuery)
    # Contruimos los campos como lista para mostrarlos en el resultado final, se usa [] ya que de lo contrario el resultado no es permanente
    fields = [i[0] for i in connection["cursor"].description]
    # empaquetamos y formateamos los campos de acuerdo a la api
    queryResult = [dict(zip(fields,row))  for row in connection["cursor"].fetchall()]
    # Finalizamos la conexion Mysql
    finish_mysql_connection(connection)
    return {
        "count":countResult[0][0],
        "result":queryResult
    }
