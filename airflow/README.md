# Airflow + MySQL Project

Este projeto configura o Airflow e MySQL usando Docker Compose. Ele permite que você execute o Airflow com o executor `LocalExecutor`, persistência de banco de dados no MySQL, e permite a instalação de pacotes adicionais usando o `requirements.txt`.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Estrutura do projeto

```bash
.
├── dags/                      # Diretório onde os DAGs do Airflow serão armazenados
├── logs/                      # Diretório onde os logs do Airflow serão gerados
├── plugins/                   # Diretório para plugins customizados do Airflow
├── requirements.txt           # Lista de dependências Python para o Airflow
├── Dockerfile                 # Dockerfile customizado para o Airflow
├── docker-compose.yml         # Arquivo de configuração do Docker Compose
└── README.md                  # Instruções do projeto
```
## Dependências

Todas as dependências Python necessárias para o Airflow são gerenciadas através do arquivo `requirements.txt`.

Exemplo de `requirements.txt`:

```text
apache-airflow-providers-airbyte
```

## Instalação e Execução

### 1. Clonar o repositório

Clone o repositório do projeto e acesse o diretório clonado:

```bash
git clone <URL_DO_SEU_REPOSITORIO>
cd <NOME_DO_DIRETORIO_CLONADO>
```
### 2. Construir e subir o ambiente

Use o `docker-compose` para construir as imagens e iniciar o ambiente:

```bash
docker-compose up --build
```
Isso irá:

- **Baixar e criar as imagens Docker para o Airflow e MySQL.**
- **Instalar as dependências listadas no `requirements.txt`.**
- **Inicializar o banco de dados do Airflow e criar um usuário admin.**


### 3. Parar e remover contêineres

Para parar e remover os contêineres, execute:

```bash
docker-compose down
```

Se quiser também remover os volumes (dados persistidos), use o comando:

```bash
docker-compose down --volumes
```

## Acessando a interface web do Airflow

Após iniciar o ambiente, a interface web do Airflow estará disponível em:

```arduino
http://localhost:8080
```
Use as seguintes credenciais para login:

- **Usuário**: `admin`
- **Senha**: `admin`

## Personalização

1. **Adicionar DAGs**  
   Coloque seus arquivos de DAG no diretório `dags/`. Eles serão automaticamente carregados pelo Airflow.

2. **Adicionar plugins**  
   Coloque seus plugins customizados no diretório `plugins/`.

3. **Instalar pacotes adicionais**  
   Se precisar instalar pacotes adicionais no Airflow, adicione-os no arquivo `requirements.txt` e reconstrua o ambiente:
```bash
docker-compose up --build -d
```
Isso garantirá que as novas dependências sejam instaladas no contêiner.

## Debug e logs

Os logs do Airflow são armazenados no diretório `logs/`. Você pode acessá-los diretamente no contêiner ou no host, dependendo do ponto de montagem.

## Problemas comuns

1. **"You need to initialize the database."**  
   Se você encontrar este erro ao iniciar o Airflow, certifique-se de que a inicialização do banco de dados foi concluída corretamente. Verifique o status dos contêineres:

   ```bash
   docker-compose ps
   ```
2. **"Se necessário, reinicie o contêiner de inicialização do Airflow:"**
    ```bash
   docker-compose run airflow-init
   ```













   









