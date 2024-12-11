from datetime import datetime
from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator
from airflow.providers.airbyte.sensors.airbyte import AirbyteJobSensor
from airflow.utils.task_group import TaskGroup


connections_airbyte = [
    ["SSO","0f1c9504-1254-4490-8a3d-9a8c6150daa7"],
    ["RESTRICAO","3451a2a5-5d6a-40f2-9322-6bdc6f96fa61"],
    ["OCORRENCIAS","21f348ed-cc53-45f0-a710-a15c1543de3a"]
]

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

with DAG(dag_id="airbyte_sync_tables_postgres",
        catchup=False,
        default_args=default_args,
        schedule="@daily",
        tags=["vizentec-engdados", "sync", "postgres"],
        doc_md=dag_doc
    ) as dag:

    start_dag = EmptyOperator(task_id="start_dag")
    end_dag = EmptyOperator(task_id="end_dag")

    task_list = []
    with TaskGroup(group_id=f"sync_schemas", dag=dag) as sync_schemas:
        for connections_airbyte in connections_airbyte:
            task_id = connections_airbyte[0]
            connection = connections_airbyte[1]

            with TaskGroup(group_id=task_id, dag=dag) as group:

                trigger_airbyte_sync = AirbyteTriggerSyncOperator(
                    task_id=f"airbyte_trigger_sync_{task_id}",
                    airbyte_conn_id="airbyte_conn",
                    connection_id=connection,
                    asynchronous=True
                )

                wait_for_sync_completion = AirbyteJobSensor(
                    task_id=f"airbyte_check_sync_{task_id}",
                    airbyte_conn_id="airbyte_conn",
                    airbyte_job_id=trigger_airbyte_sync.output
                )
                trigger_airbyte_sync >> wait_for_sync_completion

            task_list.append(group)

    start_dag >> sync_schemas >> end_dag