1: Git
Aqui la estructura esta casi como pide la rubrica con la excepcion de que no hay una carpeta de test en la raiz
directamente si no que hay diferentes test dependiendo del servicio en su carpeta correspondiente.


2: Arquitectura final
                              INTERNET
                                  |
                         +--------+--------+
                         |                 |
                   +-----+-----+           |
                   |  Central  |           |
                   |    API    |           |
                   +-----+-----+           |
                         |                 |
          +--------------+--------------+  |
          |              |              |  |
     Central DB      RabbitMQ        Workers centrales
    (Read Model)         |          (Saga, Proyeccion)
                         |                 |
        +----------------+-------+---------+-------+
        |                        |                 |
        v                        v                 v
   Warehouse 1              Warehouse 2       Warehouse 3
        |                        |                 |
        |                  Load Balancer           |
        |                        |                 |
   +----+----+              +----+----+       +----+----+
   |    |    |              |    |    |       |    |    |
  API Redis Workers       API x3 Redis Workers API Redis Workers
   |                        |                  |
   v                        v                  v
PostgreSQL              PostgreSQL         PostgreSQL
   |                        |                  |
   +------------------------+------------------+
                            |
                          Batch
                            |
                            v
                            S3
                            |
                            v
                          Lambda

