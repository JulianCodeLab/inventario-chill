pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        IMAGE_NAME = 'inventario-chill-app'
        DB_HOST = credentials('inventario-db-host')
        DB_NAME = credentials('inventario-db-name')
        DB_USER = credentials('inventario-db-user')
        DB_PASSWORD = credentials('inventario-db-password')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh 'docker build -t "${IMAGE_NAME}:${BUILD_NUMBER}" .'
            }
        }

        stage('Test') {
            agent {
                docker {
                    image 'python:3.12-slim'
                    args '-e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1'
                    reuseNode true
                }
            }
            steps {
                sh 'python -m pip install --no-cache-dir --user -r app/requirements.txt "pytest>=8,<10"'
                sh 'python -m pytest app/tests/ -v --junitxml=reports/pytest.xml'
            }
            post {
                always {
                    junit testResults: 'reports/pytest.xml', allowEmptyResults: true
                }
            }
        }

        stage('Deploy local') {
            steps {
                // La configuración adicional adapta el puerto a Docker-in-Docker.
                // Se despliega la misma imagen construida en Build, sin reconstruirla.
                sh '''
                    set -eu
                    test "$DB_HOST" = db
                    docker compose -p inventario-chill-jenkins -f docker-compose.yml -f docker-compose.jenkins.yml config --quiet
                    docker compose -p inventario-chill-jenkins -f docker-compose.yml -f docker-compose.jenkins.yml up -d --no-build --wait --wait-timeout 120
                    docker compose -p inventario-chill-jenkins -f docker-compose.yml -f docker-compose.jenkins.yml exec -T app python -c 'import urllib.request; r = urllib.request.urlopen("http://127.0.0.1:5000/", timeout=10); assert r.status == 200; print("Aplicacion: HTTP 200")'
                    docker compose -p inventario-chill-jenkins -f docker-compose.yml -f docker-compose.jenkins.yml ps
                '''
            }
        }
    }
}
