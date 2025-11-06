# tructura del Proyecto / Project Structure

## 📁 Árbol de Directorios / Directory Tree

```
EV-Charging-System/
│
├── 📂 Charging_point/          # Módulo de Punto de Carga
│   ├── 📂 Engine/              # Motor de carga - gestiona el proceso de carga
│   │   ├── EV_CP_E.py         # Programa principal del motor
│   │   ├── EngineCLI.py       # Interfaz de línea de comandos del motor
│   │   └── EngineMessageDispatcher.py  # Despachador de mensajes del motor
│   │
│   └── 📂 Monitor/             # Monitor de carga - gestiona conexiones y estado
│       ├── EC_CP_M.py         # Programa principal del monitor
│       ├── MonitorCLI.py      # Interfaz de línea de comandos del monitor
│       ├── MonitorMessageDispatcher.py  # Despachador de mensajes del monitor
│       ├── MonitorStatusPanel.py        # Panel de estado
│       └── ConnectionManager.py         # Gestor de conexiones
│
├── 📂 Core/                    # Módulo de Servicio Central
│   ├── 📂 Central/             # Servidor Central - núcleo del sistema
│   │   ├── EV_Central.py      # Programa principal del servidor central
│   │   ├── AdminCLI.py        # Interfaz de línea de comandos del administrador
│   │   ├── MessageDispatcher.py        # Despachador de mensajes
│   │   ├── ChargingPoint.py   # Gestión de puntos de carga
│   │   ├── ChargingSession.py # Gestión de sesiones de carga
│   │   └── DriverManager.py   # Gestor de conductores
│   │
│   └── 📂 BD/                  # Directorio de base de datos (reservado)
│
├── 📂 Driver/                  # Módulo de Conductor
│   ├── EV_Driver.py           # Programa principal del cliente conductor
│   ├── DriverCLI.py           # Interfaz de línea de comandos del conductor
│   └── DriverMessageDispatcher.py  # Despachador de mensajes del conductor
│
├── 📂 Common/                  # Biblioteca de Componentes Comunes
│   ├── 📂 Config/              # Módulo de configuración
│   │   ├── ConfigManager.py   # Gestor de configuración
│   │   ├── AppArgumentParser.py  # Analizador de argumentos de línea de comandos
│   │   ├── CustomLogger.py    # Logger personalizado
│   │   ├── ConsolePrinter.py  # Salida embellecida de consola
│   │   └── Status.py          # Definiciones de estado
│   │
│   ├── 📂 Database/            # Módulo de base de datos
│   │   ├── SqliteConnection.py       # Conexión SQLite
│   │   ├── BaseRepository.py         # Clase base de repositorio
│   │   ├── ChargingPointRepository.py   # Repositorio de puntos de carga
│   │   ├── ChargingSessionRepository.py # Repositorio de sesiones de carga
│   │   └── DriverRepository.py          # Repositorio de conductores
│   │
│   ├── 📂 Message/             # Módulo de mensajes
│   │   ├── MessageTypes.py    # Definición de tipos de mensajes
│   │   └── MessageFormatter.py # Herramienta de formateo de mensajes
│   │
│   ├── 📂 Network/             # Módulo de comunicación de red
│   │   ├── MySocketServer.py  # Servidor Socket
│   │   └── MySocketClient.py  # Cliente Socket
│   │
│   ├── 📂 Queue/               # Módulo de cola de mensajes
│   │   └── KafkaManager.py    # Gestor de Kafka
│   │
│   └── 📂 tools/               # Scripts de herramientas de desarrollo
│       ├── start_services_dev.bat           # Script de inicio en entorno de desarrollo
│       ├── start_services_production.bat    # Script de inicio en entorno de producción
│       ├── start_multi_charging_points.bat  # Script de inicio de múltiples puntos de carga
│       ├── start_multi_driver.bat           # Script de inicio de múltiples conductores
│       └── kafka_topic_reader.py            # Herramienta de lectura de tópicos Kafka
│
├── 📂 doc/                     # Directorio de documentación
│   ├── Practica_SD2526_EVCharging.pdf       # Documento de requisitos del proyecto
│   └── Practica SD_EVCharging_2025_2026_GuiaCorreccion.pdf  # Guía de evaluación
│
├── 📄 .env                     # Archivo de configuración de entorno
├── 📄 docker-compose.yml       # Configuración de orquestación Docker
├── 📄 requirements.txt         # Lista de dependencias Python

```

---

## 🎯 Descripción Detallada de Módulos

### 1️⃣ **Charging_point** - Módulo de Punto de Carga

Este es la implementación del sistema de punto de carga, dividido en dos submódulos:

- **Engine (Motor)**: Responsable de ejecutar el proceso real de carga

  - Procesa sesiones de carga
  - Controla el estado de carga
  - Gestiona tickets de carga
- **Monitor (Monitor)**: Responsable de la gestión de conexiones y monitoreo de estado

  - Gestiona la conexión con el servidor central
  - Monitorea el estado del punto de carga
  - Proporciona visualización del panel de estado

### 2️⃣ **Core** - Módulo de Servicio Central

El cerebro central del sistema, responsable de coordinar todos los componentes:

- **Central (Servidor Central)**:
  - Gestiona todos los puntos de carga
  - Gestiona el registro y autenticación de conductores
  - Coordina las sesiones de carga
  - Proporciona interfaz de administrador

### 3️⃣ **Driver** - Módulo de Cliente Conductor

Programa cliente para conductores de vehículos eléctricos:

- Registro e inicio de sesión de conductores
- Búsqueda de puntos de carga disponibles
- Solicitud y gestión de sesiones de carga
- Visualización del historial de cargas

### 4️⃣ **Common** - Biblioteca de Componentes Comunes

Funcionalidad común compartida por todos los módulos:

- **Config**: Gestión de configuración, logging, análisis de línea de comandos, embellecimiento de consola
- **Database**: Capa de persistencia de datos (SQLite + patrón Repository)
- **Message**: Definición de tipos de mensajes y formateo
- **Network**: Comunicación Socket (cliente/servidor)
- **Queue**: Gestión de cola de mensajes Kafka
- **tools**: Scripts auxiliares de desarrollo y ejecución

---

## 🔄 Flujo de Arquitectura del Sistema

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Driver    │◄───────►│ EV Central   │◄───────►│  Charging   │
│ (Conductor) │  Socket  │   (Central)  │  Socket  │    Point    │
│             │          │              │          │   (Punto)   │
└─────────────┘         └──────┬───────┘         └─────────────┘
                               │
                               ▼
                        ┌─────────────┐
                        │   Kafka     │
                        │(Cola Msjs.) │
                        └─────────────┘
                               │
                               ▼
                        ┌─────────────┐
                        │   SQLite    │
                        │(Base Datos) │
                        └─────────────┘
```

---

## 🚀 Inicio Rápido / Quick Start

### Entorno de Desarrollo (Development)

```bash
Common/tools/start_services_dev.bat
```

Orden de inicio:

1. EV Central (Servidor Central)
2. CP Engine (Motor del Punto de Carga)
3. CP Monitor (Monitor del Punto de Carga)
4. EV Driver (Cliente Conductor)

### Entorno de Producción (Production)

```bash
Common/tools/start_services_production.bat
```

### Usando Docker para inicializar kafka

```bash
docker-compose up -d
```

---

## 📦 Stack Tecnológico / Tech Stack

- **Lenguaje**: Python 3.x
- **Comunicación de Red**: Socket (TCP/IP)
- **Cola de Mensajes**: Apache Kafka
- **Base de Datos**: SQLite
- **Gestión de Dependencias**: requirements.txt
- **Contenedorización**: Docker & Docker Compose
- **Embellecimiento de Consola**: Biblioteca Rich

---
