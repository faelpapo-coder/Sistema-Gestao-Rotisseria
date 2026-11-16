# Sistema de Gestão da Rotisseria

MVP acadêmico desenvolvido em Python 3.12, Flask e SQLite para apoiar a rotina de uma rotisseria.

## Funcionalidades

- Painel inicial com resumo de pedidos, clientes, produtos e vendas concluídas.
- Cadastro e consulta de clientes.
- Cadastro de produtos com preço e quantidade em estoque.
- Cadastro de pedidos com cliente, produto e quantidade.
- Baixa automática do estoque ao registrar um pedido.
- Atualização do status: Aguardando preparo, Em preparo, Pronto, Concluído ou Cancelado.
- Histórico de pedidos.

## Requisitos

- Python 3.12 ou superior
- pip

## Como executar

1. Baixe ou clone este repositório.
2. Abra o terminal na pasta do projeto.
3. Crie um ambiente virtual:

   ```bash
   python -m venv .venv
   ```

4. Ative o ambiente virtual:

   **Windows**
   ```bash
   .venv\Scripts\activate
   ```

   **Linux/macOS**
   ```bash
   source .venv/bin/activate
   ```

5. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

6. Inicie o sistema:

   ```bash
   python app.py
   ```

7. Acesse no navegador: http://127.0.0.1:5000

O banco `rotisseria.db` é criado automaticamente na primeira execução.

## Fluxo recomendado para testar

1. Cadastre um cliente (ex.: João Silva).
2. Cadastre um produto (ex.: Marmita de frango), com preço e estoque.
3. Acesse Pedidos e registre o pedido do cliente.
4. Atualize o status do pedido e consulte o Histórico.

## Estrutura

```text
Sistema-Gestao-Rotisseria/
├── app.py
├── requirements.txt
├── README.md
├── rotisseria.db       # criado automaticamente ao executar
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── customers.html
│   ├── products.html
│   ├── orders.html
│   └── history.html
├── static/
│   └── style.css
└── tests/
```

## Observações

Este projeto é um MVP educacional. Antes de uso real, é necessário configurar uma chave secreta segura, autenticação e autorização de usuários, proteção contra CSRF, validações adicionais, política de backups e testes mais abrangentes. Não utilize dados pessoais reais durante a demonstração acadêmica.
