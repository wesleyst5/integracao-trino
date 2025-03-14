from datetime import datetime
from pytz import timezone
from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.providers.trino.hooks.trino import TrinoHook
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "vizentec-engdados",
    "start_date": datetime(2024, 9, 18),
    "email_on_failure": False,
    "email_on_retry": False,
    "email": "" #Variable.get("com.vizentec.engdados.email_list", deserialize_json=True),
}

dag_doc = """
### Sync Tables Postgres
    The Orchestration process is the folowing:
    1 - Atualiza registros pendentes (status = 0 → 1)
    2 - Busca registros no Cassandra e insere no S3 (extract_fluxo).
    3 - Wait for sync completion
    4 - Atualiza o status para 2 na tabela de controle (update_status).
    
"""

# Função para atualizar registros pendentes (status = 0 → 1)
def update_pending_records():
    hook = TrinoHook(trino_conn_id='trino_default')
    sql = """
        UPDATE postgres.public.controle_fluxo
        SET status = 1
        WHERE status = 0
    """
    hook.run(sql)

# Função para buscar equipamentos e intervalos no PostgreSQL via Trino
def get_equipamentos():
    hook = TrinoHook(trino_conn_id='trino_default')
    sql = """
        SELECT codigoEquipamento, dataHoraInicioFluxoMs, dataHoraFimfluxoMs
        FROM postgres.public.controle_fluxo
        WHERE status = 1
    """
    return hook.get_pandas_df(sql).to_dict(orient='records')

# Função para buscar registros no Cassandra e escrever no S3 particionado
def extract_fluxo(**kwargs):
    hook = TrinoHook(trino_conn_id='trino_default')
    equipamentos = kwargs['ti'].xcom_pull(task_ids='get_equipamentos')

    for equip in equipamentos:
        codigo = equip['codigoEquipamento']
        dt_inicio = equip['dataHoraInicioFluxoMs']
        dt_fim = equip['dataHoraFimfluxoMs']

        sql = f"""
            INSERT INTO s3.default.fluxo (equipamento, data_hora, ano_mes)
            SELECT
                equipamento,
                data_hora,
                date_format(from_unixtime(data_hora / 1000), '%Y-%m') AS ano_mes
            FROM cassandra.fluxokeyspace.fluxo_equipamento_data
            WHERE equipamento = '{codigo}'
            AND data_hora BETWEEN {dt_inicio} AND {dt_fim}
        """
        hook.run(sql)

# Função para atualizar o status dos registros no PostgreSQL
def update_status(**kwargs):
    hook = TrinoHook(trino_conn_id='trino_default')
    equipamentos = kwargs['ti'].xcom_pull(task_ids='get_equipamentos')

    for equip in equipamentos:
        codigo = equip['codigoEquipamento']
        dt_inicio = equip['dataHoraInicioFluxoMs']
        dt_fim = equip['dataHoraFimfluxoMs']

        sql = f"""
            UPDATE postgres.public.controle_fluxo
            SET status = 2
            WHERE codigoEquipamento = '{codigo}'
            AND dataHoraInicioFluxoMs = {dt_inicio}
            AND dataHoraFimfluxoMs = {dt_fim}
        """
        hook.run(sql)

with DAG(dag_id="trino_sync_fluxo",
         catchup=False,
         default_args=default_args,
         schedule="@daily",
         tags=["vizentec-engdados", "sync", "fluxo"],
         doc_md=dag_doc
        ) as dag:

    start_dag = EmptyOperator(task_id="start_dag")
    end_dag = EmptyOperator(task_id="end_dag")

    #Atualizar registros com status 0 para 1
    update_pending_records_task = PythonOperator(
        task_id='update_pending_records',
        python_callable=update_pending_records
    )

    #Buscar equipamentos e intervalos no PostgreSQL via Trino
    get_equipamentos_task = PythonOperator(
        task_id='get_equipamentos',
        python_callable=get_equipamentos
    )

    #Buscar registros no Cassandra e salvar no S3 particionado
    extract_fluxo_task = PythonOperator(
        task_id='extract_fluxo',
        python_callable=extract_fluxo,
        provide_context=True
    )

    # 4️ Atualizar status para "2" na tabela de controle
    update_status_task = PythonOperator(
        task_id='update_status',
        python_callable=update_status,
        provide_context=True
    )

    start_dag >> update_pending_records_task >> get_equipamentos_task >> extract_fluxo_task >> update_status_task >> end_dag