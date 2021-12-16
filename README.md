# Introduccion
El presente repositorio pretende completar las pruebas tecnicas solicitadas por el equipo de desarrollo de  Habi para el proceso de seleccion.

## Parte I - Practica - API

En esta parte, veo que la solicitud es de la creacion de una REST API usando Python, en formato de microservice. Despues de meditarlo un poco, creo que la mejor solucion para esta tarea seria primero separando la logica de web de la logica del proceso, dejando asi un archivo/libreria que pueda moverse o incorporarse con otros proyectos mas adelante y que permitan que el codigo sea reciclable y de relativo sencillo entendimiento.

Siguiendo esa logica, usare entonces Flask como motor web durante la etapa de desarrollo web, ya que por su naturaleza permite despues ser reemplazado por uWSGI o incluso ser adaptado como Lambda en AWS o incluso como servicio usando Systemd.

Adicionalmente y para tener un microservicio que pueda ser implementado no solo en AWS sino en varias otras plataformas, como Google Cloud, Microsoft Azure e incluso desplegado en una infraestructura dedicada (OVH,100TB,etc.) o utilizando un orquestador como kubernetes, se decide utilizar Docker como plataforma de virtualizacion/contenedor.

Como parte final, para el microservicio final, decido utilizar Nginx como proxy WSGI dentro del respectivo contenedor docker, esto para mostrar un ejemplo de arquitectura, pero dejando tambien abierta la posiblidad de que se pueda dejar el contenedor docker solo como servidor WSGI (sin Nginx) modificando un de archivo de configuracion y modificando el Dockerfile. 

Para la configuracion de las credenciales de la base de datos, se utiliza el enfoque de almacenarlas como variables de entorno, por lo que pienso permitir dos enfoques:

- Utilizar un archivo .env con las variables de entorno a usar y la libreria `dotenv` en el archivo principal para leer las mismas, generando asi que las variables esten dentro del contenedor unicamente

- Utilizar las variables de entorno asignadas durante la ejecucion del contenedor, por lo que implicaria modificar el codigo para omitir la lectura del archivo .env durante la ejecucion del mismo, dejando las variables a ser asignadas por la ejecucion del contenedor

Ya tomando esas consideraciones y decisiones en cuenta, procedo a las siguientes actividades.

### Analisis de Base de datos

Para reducir la carga en el servidor de RDS del cual se me proporcionaron las credenciales, decido hacer un `mysqldump` de la base de datos actual para tener una mejor visibilidad de las estructuras de los datos. Asi mismo procedo a importar el respectivo dump a un servidor en localhost para poder continuar con las respectivas pruebas

#### Extraccion de base remota
```bash
$ mysqldump --no-tablespaces  --column-statistics=0 --single-transaction -u[aws_user] -p -h [aws_host] -P [aws_port] [aws_db] > dbase.sql
```
Se utilizan las opciones `--no-tablespaces` ,`--column-statistics=0` y `--single-transaction` para exportar correctamente dados los permisos con los que contamos

#### Creacion de usuario y base de datos en servidor local
```sql
CREATE USER 'database_user'@'%' IDENTIFIED BY 'database_user_password';
CREATE DATABASE habi_api;
GRANT ALL PRIVILEGES ON habi_db.* TO 'database_user'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
```
#### Importacion de datos externos a base de dato local
```bash
$ mysql -u[local_user] -p -h [local_host] -P [local_port] [local_db] < dbase.sql
```

#### Estructura encontrada

Revisando ya el resultado del dump, puedo ver mejor la estructura de la base, encontrando las tablas a utilizar:

```sql
CREATE TABLE `property` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `address` varchar(120) NOT NULL,
  `city` varchar(32) NOT NULL,
  `price` bigint(20) NOT NULL,
  `description` text,
  `year` int(4) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `property_id_uindex` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=latin1;

CREATE TABLE `status` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(32) NOT NULL,
  `label` varchar(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `status_historial_name_uindex` (`name`),
  UNIQUE KEY `status_historial_id_uindex` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=latin1;

CREATE TABLE `status_history` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `property_id` int(11) NOT NULL,
  `status_id` int(11) NOT NULL,
  `update_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `status_historial_id_uindex` (`id`),
  KEY `status_historial_property_id_fk` (`property_id`),
  KEY `status_historial_status_id_fk` (`status_id`),
  CONSTRAINT `status_historial_property_id_fk` FOREIGN KEY (`property_id`) REFERENCES `property` (`id`),
  CONSTRAINT `status_historial_status_id_fk` FOREIGN KEY (`status_id`) REFERENCES `status` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=36 DEFAULT CHARSET=latin1;
```

Veo entonces la relacion entre las tres tablas y propongo lo siguiente:

- Si bien la solicitud indica que los filtros requeridos son: Año de construcción, Ciudad, Estado. Viendo el esquema veo que se puede ampliar a filtrar por ID, descripcion y direccion, por lo que se incluyen los campos en los filtros posibles
- Defino 3 tipos de datos que podemos filtrar:
    - numeros: como el año de contruccion, el precio y el id 
    - textos: como direccion, ciudad, descripcion
    - texto fijo: en este caso solo el campo `status` o estado esta aqui, ya que las consulta de estado solo deberian permitir un rango especifico de valores

Encuentro una restriccion interesante, y es que en la tabla de `status` es donde tenemos el valor de los posibles valores de estado de la propiedad, mientras que en `status_history` solo almacenamos el ID del mismo, por lo que despues de jugar con algunas combinaciones posibles, defino que el modelo de datos que me es mas como a usar seria algo similar a:
```
id,address,city,price,description,year,status
```
Y por lo tanto el campo status seria el ultimo estado de la propiedad en formato de texto

Despues de un analisis y algunas pruebas, genero una sentencia SQL inicial que me puede dar el formato deseado y que permite un filtrado sencillo:

```sql
SELECT a.* , d.name as `status`
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
;
```

Como se puede observar, en el mismo comando estoy incluyendo las validaciones para solo incluir los estados permitidos indicados en el documento de solicitud.

A partir de esta solicitud inicial, podemos empezar a crear la libreria de filtros

### Creacion de Filtros

Una vez que tenemos el documento basico, podemos ir generando una estructura para los campos a filtrar, se propone por lo tanto el siguiente modelo para las comunicaciones entre frontend y backend:

#### Parametros de Entrada:
- *fields*: Array de Strings de los campos a mostrar,esto permite que la API no solo muestre siempre los mismos campos, sino que permite que el frontend decida que campos desea recibir, y esto ayuda a que el mismo endpoint pueda usarse por ejemplo para un catalogo de busqueda y por ejemplo un plugin,etc. Asi mismo, al poder escoger los campos a mostrar se puede reducir el consumo de ancho de banda entre los equipos.  En caso de que el campo se encuentre vacio, nulo o no definido se mostraran todos los campos. Valores posibles: id,address,city,price,description,year,status

- *filters*: Array de Objetos con los parametros a usar como filtro

    - *field* (obligatorio): Campo sobre el que se aplicara el filtro (string). Se usan los mismos valores que en `fields`.Valores posibles: id,address,city,price,description,year,status

    - *type* (obligatorio): Tipo de filtro que se aplicara, valores posibles (string):
        - "equal"   Buscar el valor exacto (Comparacion "=")
        - "sign"    Buscar usando un signo de comparacion (Comparacion "=","<","<=",">",">=")
        - "partial" Buscar parte del contenido del valor del campo (Comparacion LIKE '%texto_a_buscar%')
        - "rank"    Buscar entre un rango de valores (Comparacion campo>=limite_inferior AND  campo<=limite_superior)
        - "in"      Encuentra los valores que coincidan con un array. (Comparacion campo IN (valor1,valor2,valor3) )

    - *sign* (opcional): Solo obligatorio si el tipo de filtro (type) es "sign" (string). Valores posibles: "=","<","<=",">",">="

    - *value* (obligatorio)         Valor con el cual hacer la comparacion. El tipo de valor puede ser number, string o array. 
        - En caso de que el tipo de filtro sea "rank", el valor debe ser un Array que contenga el par [Valor_minimo,Valor_maximo] ambos de tipo numerico. 
        - Los campos a filtrar number y text el tipo de dato enviado debera coincidir con el tipo de valor que se encuentra en el campo filtrado (string, number, etc).
        - En caso de que el tipo de filtro sea "in", el valor debe ser un Array que contenga los valores (texto o numerico) en los cuales el valor pueda estar, por ejemplo, ["preventa","venta"]

- *order*: Array de objetos con los paramtros de orden
    - *field*      Nombre del campo sobre el cual efectuar el ordenamiento (String).
    - *direction*  Tipo de ordenamiento (string). Valores posibles "asc" para orden ascendente, "desc" para orden descendente

- *start*: Devolver resultados a partir de este ordenado (int). Equivalente a LIMIT start,length en MySQL.

- *length*: Numero de resultados devolver (int). Equivalente a LIMIT start,length en MySQL.

#### Parametros de la respuesta
   - *count*: Total de Resultados Filtrados (incluye el resultado de filtrar y se puede usar como auxiliar en temas de paginado, no solo los que se solicitan en length)
   - *result*: Arreglo del resultado con los campos solicitados

##### Ejemplo de JSON de Consulta

```json
{
    "fields":["id","address","status"],
    "filters":[
        {
            "field":"id",
            "type":"sign",
            "value":5,
            "sign":">"
        },
        {
            "field":"status",
            "type":"in",
            "value":["en_venta","vendido"]
        }
    ],
    "order":[
        {"field":"id","direction":"desc"},
        {"field":"city","direction":"desc"}
    ],
    "start":3,
    "length":100
}
```

##### Resultado Esperado

```json
{
    "success": true,
    "data": {
        "count": 9,
        "result": [
            {
                "id": 22,
                "address": "Bloque 5 C26 Umbras",
                "status": "pre_venta"
            },
            {
                "id": 21,
                "address": "M1 C5 Panorama",
                "status": "pre_venta"
            },
            {
                "id": 20,
                "address": "Entrada 2 via cerritos",
                "status": "pre_venta"
            },
            {
                "id": 19,
                "address": "Entrada 3 via cerritos",
                "status": "pre_venta"
            },
            {
                "id": 18,
                "address": "Maracay casa 24",
                "status": "en_venta"
            },
            {
                "id": 17,
                "address": "Malabar entrada 2",
                "status": "en_venta"
            },
            {
                "id": 16,
                "address": "Cll 1A #11B-20",
                "status": "vendido"
            },
            {
                "id": 10,
                "address": "calle 95 # 78 - 49",
                "status": "pre_venta"
            },
            {
                "id": 7,
                "address": "carrera 100 #15-90",
                "status": "pre_venta"
            }
        ]
    },
    "message": "Results Found"
}
```

### Proceso de creacion de filtros

Una vez decidido el esquema a usar en respuesta/solicitud, procedemos a definir los tipos de datos que cada campo puede soportar, definiendo entonces la estructura:

```json
{
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
```

Definiendo entonces el esquema de datos de la siguiente forma:
- *key*: Seria el nombre "publico" del campo indicando tambien los campos que podemos usar
    - *realField*: Seria el nombre real en la estructura de datos (tomando como base el query que creamos en los pasos anteriores)
    - *type*: Indica el tipo de dato esperado y al mismo tiempo las posibles validaciones a recibir

Y definiendo las validaciones y filtros aplicables por tipo de datos de la siguiente forma:
```json
{
    "number":["equal","sign","rank","in"],
    "text_exact":["equal","in"],
    "text":["equal","partial","in"]
}
```

### Consideraciones de seguridad

Debido a la naturaleza de la API (filtrar), se utiliza la funcion de C de la libreria de mysql.connector ._cmysql.escape_string(str) para hacer un parse de los campos de texto y evitar posibles injecciones de codigo


### Inicializacion del entorno de desarrollo

Iniciamos creando una carpeta llamada src donde ira nuestro codigo, en esa carpeta colocamos nuestro archivo `main.py` que puede ser invocado tanto por Flask y uWSGI para produccion. Y adicionalmente creamos una carpeta src/library donde colocamos nuestro archivo `list.py` que contiene la logica de los filtros

Para arrancar el entorno de desarrollo ingresamos:
```bash
cd src/
python3 main.py
```
Lo que nos iniciara una instancia en el puerto 5000, con el que podemos proceder a las pruebas 

### Conversion a uWSGI

Una vez probado el servicio, procedemos a crear el archivo `uwsgi.ini` donde configuramos los parametros de inicializacion, de esta forma podemos iniciar el servicio de uwsgi usando el comando:
```bash
uwsgi --ini uwsgi.ini
```
Con lo que se iniciaria el servicio de uWSGI en el socket /tmp/uwsgi.socket

**Nota Importante**: se asume que el codigo se encuentra en la carpeta /srv/flask_app/src en caso de lo contrario se debera modificar el campo `chdir` en el archivo uwsgi.ini

### Agregando Nginx

Creamos una configuracion de prueba en Nginx en el directorio /etc/nginx para servir el socket uWSGI en el puerto 80

```
user www-data;
worker_processes auto;
pid /run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    access_log /dev/stdout;
    error_log /dev/stdout;

    sendfile            on;
    tcp_nopush          on;
    tcp_nodelay         on;
    keepalive_timeout   65;
    types_hash_max_size 2048;

    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    index   index.html index.htm;

    server {
        listen       80 default_server;
        listen       [::]:80 default_server;
        server_name  localhost;
        root         /var/www/html;

        location / {
            include uwsgi_params;
            uwsgi_pass unix:/tmp/uwsgi.socket;
        }
    }
}

```

### Dockerizando Codigo

Primero que nada creamos nuestro archivo de dependencias "requirements.txt" para automatizar la instalacion de las mismas en python.

Luego creamos nuestro Dockerfile con las respectivas instrucciones. En este caso usamos la imagen python:3.6-slim que utiliza la version de Debian 11. Con lo que podemos proceder a la configuracion de las dependencias de sistema:
```
...
RUN apt-get clean \
    && apt-get -y update

RUN apt-get -y install nginx \
    && apt-get -y install python3-dev \
    && apt-get -y install build-essential
...
```
Con esto teniendo las dependencias de sistema minimas para la instalacion de uwsgi y demas

Por ultimo creamos el archivo que iniciara los servicios uWSGI y Nginx dentro del contenedor, y le llamamos `start.sh`
```bash
#!/usr/bin/env bash
service nginx start
uwsgi --ini uwsgi.ini
```

Compilamos la imagen
```bash
docker build --tag habi_api_rest .
```
y la ejecutamos de la siguientes posibles formas:

- Si queremos que las variables de entorno esten asignadas por el entorno docker, [y ya modificamos el codigo para omitir la lectura del archivo .env]
```bash
docker run -p 80:80 --env-file src/.env habi_api_rest
```
- Si queremos usar el archivo .env dentro del contenedor
```bash
docker run -p 80:80 habi_api_rest
```

#### Notas finales de Dockerizado
- Se incluyen archivos para dockerizar sin nginx
- Se incluen en el codigo las observaciones para la modificacion de las variables de entorno y demas

### Propuesta para mejorar la velocidad de las consultas

Se proponen dos posibles cambios al esquema actual para reducir la velocidad de las consultas

#### Propuesta 1 - Agregar campo de `status`

Seria agregar a la tabla `property` el campo `status` que almacenaria el id del ultimo estado conocido de la propiedad

```sql
ALTER TABLE `property`  ADD COLUMN `status` int(11) NOT NULL ; 
ALTER TABLE `property`  ADD FOREIGN KEY (`status`) REFERENCES `status`(`id`);
```

Implicaria cambiar la logica del servicio que almacena/actualiza el estado, pero con esto podriamos tener una consulta mas rapida respecto al historial ya que hariamos un JOIN menos

#### Propuesta 2 - Agregar campo de `last_status`

Seria agregar a la tabla `property` el campo `last_status` que almacenaria el id del ultimo estado conocido de la propiedad respecto a la tabla `status_history`

```sql
ALTER TABLE `property`  ADD COLUMN `last_status` int(11) NOT NULL ; 
ALTER TABLE `property`  ADD FOREIGN KEY (`last_status`) REFERENCES `status_history`(`id`);
```

Implicaria cambiar la logica del servicio que almacena/actualiza el estado, pero con esto podriamos tener una consulta mas rapida respecto al historial ya que el JOIN que busca el ultimo registro seria reemplazado por un JOIN directo en vez de un JOIN de un select, es decir no se requeriria el uso de una tabla virtual.

**IMPORTANTE** Se incluye la carpeta de pruebasJSON con posibles formas de uso. No olvide configurar sus variables de entorno ya sea en el archivo .env dentro de src/ o en la ejecucion de sus comandos

## Parte II - Teorica - Boton Like

El esquema propuesto es sencillo y consta de solo una tabla indicando que usuario ha dado like a que propiedad (opcional, fecha del like)
```sql
CREATE TABLE `likes_history` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `property_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `like_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  KEY `property_id` (`property_id`),
  KEY `user_id` (`status_id`),
  CONSTRAINT `property_id` FOREIGN KEY (`property_id`) REFERENCES `property` (`id`),
  CONSTRAINT `user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=36 DEFAULT CHARSET=latin1;
```
* Ver archivo MERLike.png

Se propone esta estructura ya que de esta forma podemos tener no solo un historial de likes, sino que permite generar reportes de propiedades mas gustadas no solo de forma global, sino en linea de tiempo, guardando pocos datos y por lo mismo teniendo consultas ligeras.









