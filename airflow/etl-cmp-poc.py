# airflow imports
from airflow.decorators import dag, task
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.providers.oracle.hooks.oracle import OracleHook
from airflow.operators.bash import BashOperator
from docker.types import Mount
from kafka import KafkaConsumer
from airflow.models import Variable
# astro imports
from astro.files import File
from astro.table import Table, Metadata
from astro.sql.operators.load_file import load_file
# cosmos imports
from cosmos import (
    ProjectConfig,
    DbtTaskGroup
)

from datetime import datetime
import json

from include.profiles import postgres_profile
from include.constants import DBT_PROJECT_PATH, CASSANDRA_ENV, DEFAULT_ARGS

KAFKA_TOPIC = "cmp_fluxo_sucess"
DAG_GROUP_ID = "airflow_listener"

file_name = 'temp_{}.parquet'.format(
    datetime.now().strftime('%d%m%y'))

def get_codigo_equipamento(df, arquivo_id):

    codigo_equipamento = df[df["ARQUIVO_ID"] == arquivo_id]["CODIGO_EQUIPAMENTO"].values.tolist()
    if codigo_equipamento:
        return codigo_equipamento[0]
    else:
        return None

@dag(
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    dag_id='etl-cmp-vzt-poc',
    tags=['cmp', 'campinas', 'ingestão'],
    default_args=DEFAULT_ARGS,
    max_active_runs=2
)
def etl_cmp_vzt_poc():

    @task
    def get_new_messages() -> list[dict]:
        consumer = KafkaConsumer(
            bootstrap_servers=[Variable.get("KAFKA_BOOTSTRAP_SERVERS")],
            client_id=Variable.get("KAFKA_CLIENT_ID"),
            group_id=DAG_GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=1000
        )
        consumer.subscribe(topics=[KAFKA_TOPIC])
        while not consumer.assignment():
            consumer.poll(timeout_ms=100)

        messages = []
        for msg in consumer:
            messages.append(
                json.loads(msg.value))

        consumer.close()

        return messages

    @task
    def get_arquivo_id(messages: list[dict]):
        ids = [msg["id"] for msg in messages]
        oracle_hook = OracleHook(oracle_conn_id="oracle_dtf")
        data = oracle_hook.get_pandas_df(
            sql="""
                SELECT 
                    CODIGO_EQUIPAMENTO, ARQUIVO_ID
                FROM CMP_DEBUG.TBARQUIVO 
                WHERE ARQUIVO_ID IN ({})""".format(
                str(ids).replace("[", "").replace("]", ""))
        )

        for dicionario in messages:
            arquivo_id = dicionario["id"]
            codigo_equipamento = get_codigo_equipamento(data, arquivo_id)
            if codigo_equipamento:
                dicionario["codigoEquipamento"] = codigo_equipamento

        return messages

    get_arquivo_id = get_arquivo_id(get_new_messages())

    @task
    def get_ingestion_parameters(contexts: list[dict]):

        commands = []
        for context in contexts:
            command = ["poetry", "run", "python", "app/main.py", "ingest", "cassandra",
                       "fluxokeyspace.fluxo_equipamento_data", context.get('codigoEquipamento'),
                       context.get('dataHoraInicioFluxo'), context.get('dataHoraFimfluxo')]
            commands.append(command)

        return commands

    get_ingestion_parameters = get_ingestion_parameters(get_arquivo_id)

    clean_temp_folders = BashOperator(
        task_id='clean_temp_folders',
        bash_command=
        "rm -rf /usr/local/airflow/include/temp/cassandra/* && rm -rf /usr/local/airflow/include/temp/result/*"
    )

    ingest_cassandra = DockerOperator.partial(
        task_id='fetch_cassandra',
        image='imagem_teste:0.2.0',
        auto_remove=True,
        mount_tmp_dir=False,
        environment=CASSANDRA_ENV,
        mounts=[
            Mount(source='/opt/astro/include/temp/',
                  target='/app/data/', type="bind")
        ]
    ).expand(
        command=get_ingestion_parameters
    )

    merge_parquet_files = DockerOperator(
        task_id='DOs',
        image='imagem_teste:0.2.0',
        auto_remove=True,
        mount_tmp_dir=False,
        environment=CASSANDRA_ENV,
        mounts=[
            Mount(source='/opt/astro/include/temp/',
                  target='/app/data/', type="bind")
        ],
        command=["poetry", "run", "python", "app/main.py", "merge-files"]
    )

    insert_to_postgres = load_file(
        task_id='insert_to_postgres',
        input_file=File(path='/usr/local/airflow/include/temp/result/{}'.format(file_name)),
        output_table=Table(name="fluxo_teste_airflow", conn_id="pg_cmp",
                           metadata=Metadata(schema="raw")),
        if_exists='append',
        # assume_schema_exists=True
    )

    dbt_source = DbtTaskGroup(
        group_id="dbt_project",
        project_config=ProjectConfig(
            dbt_project_path=(DBT_PROJECT_PATH / "vzt_poc")),
        operator_args={"install_deps": True},
        profile_config=postgres_profile,
        # render_config=RenderConfig(select=["path:models/source"])
    )

    [clean_temp_folders, get_ingestion_parameters] >> ingest_cassandra >> merge_parquet_files
    merge_parquet_files >> insert_to_postgres >> dbt_source

etl_cmp_vzt_poc()