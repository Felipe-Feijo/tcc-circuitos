1. Criando o ambiente virtual (venv)
Criar:
python -m venv venv

Ativar (Windows):
venv\Scripts\activate

Desativar:
deactivate

2. Instalando dependências do projeto

Com o ambiente virtual ativo:

pip install -r requirements.txt


Se for a primeira vez que o projeto é clonado, o venv deve ser criado antes:

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

3. Gerenciamento de dependências usando pip-tools

Este projeto utiliza pip-tools para manter as dependências organizadas.

Instalar pip-tools:
pip install pip-tools

Arquivos usados:
requirements.in

Lista apenas as dependências diretas do projeto.
Exemplo:

PyQt6
numpy
matplotlib

requirements.txt

É gerado automaticamente com todas as dependências resolvidas e versões travadas.

4. Gerando o requirements.txt

Sempre que mudar o requirements.in, rode:

pip-compile requirements.in


Isso cria/atualiza o requirements.txt.

5. Adicionando uma nova biblioteca

Instale a biblioteca:

pip install <biblioteca>


Adicione no requirements.in:

PyQt6-Charts


Recompile a lista:

pip-compile requirements.in


Atualize o repo:

git add requirements.in requirements.txt
git commit -m "Atualiza dependências"
git push

6. Fluxo de trabalho ao trocar de máquina
Antes de começar a trabalhar:
git pull

Ao abrir em uma máquina nova:
git clone https://github.com/usuario/repositorio.git
cd repositorio
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt


Agora o ambiente está idêntico.