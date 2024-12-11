

from datetime import datetime
from airflow import DAG
from airflow.models import Variable
from airflow.utils.task_group import TaskGroup
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from kafka import KafkaConsumer
import json
import pandas as pd
from cassandra.cluster import Cluster
from io import BytesIO
from airflow.hooks.base import BaseHook
from cassandra.auth import PlainTextAuthProvider



default_args = {
    "owner": "vizentec-engdados",
    "start_date": datetime(2024, 9, 14),
    "email_on_failure": False,
    "email_on_retry": False,
    "email": "" #Variable.get("com.vizentec.engdados.email_list", deserialize_json=True),
}

dag_doc = """
### Sync Tables Postgres
    The Orchestration process is the folowing:
    1 - Start Sync tables postgres to landing S3
    2 - Wait for sync completion
"""


# Função para consumir mensagens do Kafka
def consume_kafka_messages(**kwargs):
    consumer = KafkaConsumer(
        'nome_do_topico',
        bootstrap_servers=['localhost:9092'],
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='airflow-group'
    )
    messages = []
    for message in consumer:
        messages.append(json.loads(message.value.decode('utf-8')))
        # Limite de mensagens para evitar consumo excessivo em um ciclo
        if len(messages) >= 10:
            break
    consumer.close()
    return messages


# Função para consultar o PostgreSQL usando IDs
def query_postgres(ids, **kwargs):
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    id_list = tuple(ids)
    query = f"SELECT CODIGO_EQUIPAMENTO, ARQUIVO_ID FROM DEBUG.TBARQUIVO WHERE ARQUIVO_ID IN {id_list}"
    records = pg_hook.get_records(query)
    return [{"CODIGO_EQUIPAMENTO": r[0], "ARQUIVO_ID": r[1]} for r in records]


# Função para consultar o Cassandra e obter dados baseados no equipamento e intervalo de tempo
def query_cassandra(equipamentos, data_inicio, data_fim, **kwargs):

    # Recupera as credenciais do Airflow
    cassandra_conn = BaseHook.get_connection('cassandra_default')
    auth_provider = PlainTextAuthProvider(
        username=cassandra_conn.login,
        password=cassandra_conn.password
    )

    cluster = Cluster([cassandra_conn.host], auth_provider=auth_provider)
    session = cluster.connect(cassandra_conn.schema)

    records = []
    for equipamento in equipamentos:
        query = f"""
            SELECT * FROM fluxo_equipamento_data
            WHERE CODIGO_EQUIPAMENTO = '{equipamento}'
            AND dataHora BETWEEN '{data_inicio}' AND '{data_fim}'
            ALLOW FILTERING;
        """
        rows = session.execute(query)
        for row in rows:
            records.append(dict(row))
    cluster.shutdown()
    return records

# Função para salvar os dados no S3 no formato Parquet
def save_to_s3(records, **kwargs):
    if records:
        s3_hook = S3Hook(aws_conn_id='aws_default')
        df = pd.DataFrame(records)
        buffer = BytesIO()
        df.to_parquet(buffer, engine='pyarrow')

        # Definindo o nome do arquivo com ARQUIVO_ID e CODIGO_EQUIPAMENTO
        arquivo_id = records[0].get("ARQUIVO_ID", "sem_id")
        codigo_equipamento = records[0].get("CODIGO_EQUIPAMENTO", "sem_codigo")
        now = datetime.now()
        file_name = f"{now.year}-{now.month:02}-{now.day:02}/{arquivo_id}_{codigo_equipamento}.parquet"

        # Salvando no bucket S3
        s3_hook.load_bytes(buffer.getvalue(), key=file_name, bucket_name='meu_bucket', replace=True)


# Criação da DAG
with DAG(dag_id="airbyte_sync_fluxos",
        catchup=False,
        default_args=default_args,
         description='Consome Kafka, consulta PostgreSQL e Cassandra, e grava no S3 em formato Parquet',
        schedule="@daily",
        tags=["vizentec-engdados", "sync", "postgres"],
        doc_md=dag_doc
    ) as dag:

    start_dag = EmptyOperator(task_id="start_dag")
    end_dag = EmptyOperator(task_id="end_dag")

    # Consumindo mensagens do Kafka
    kafka_task = PythonOperator(
        task_id='consume_kafka',
        python_callable=consume_kafka_messages
    )

    # Consultando o PostgreSQL
    postgres_task = PythonOperator(
        task_id='query_postgres',
        python_callable=query_postgres,
        op_args=[kafka_task.output]
    )

    # Consultando o Cassandra
    cassandra_task = PythonOperator(
        task_id='query_cassandra',
        python_callable=query_cassandra,
        op_args=[postgres_task.output, '{{ ti.xcom_pull(task_ids="consume_kafka")[0]["dataHoraInicioFluxo"] }}',
                 '{{ ti.xcom_pull(task_ids="consume_kafka")[0]["dataHoraFimfluxo"] }}']
    )

    # Salvando os dados no S3 em formato Parquet
    s3_task = PythonOperator(
        task_id='save_to_s3',
        python_callable=save_to_s3,
        op_args=[cassandra_task.output]
    )

    # Definindo a ordem das tarefas
    kafka_task >> postgres_task >> cassandra_task >> s3_task

