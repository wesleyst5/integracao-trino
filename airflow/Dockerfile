FROM apache/airflow:2.9.3

# Copiar o arquivo requirements.txt para o contêiner
COPY requirements.txt .

# Instalar dependências listadas no requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
