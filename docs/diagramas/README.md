# Diagramas

Diagramas UML do projeto em formato PlantUML (`.puml`).

## Arquivos

| Arquivo | Tipo | Descrição |
|---|---|---|
| `seq_orquestracao.puml` | Sequência | Orquestração de um passo de simulação: StepScheduler → SimulationController → engine → ViewSync → HistoryManager |
| `seq_engine.puml` | Sequência | Loop interno do motor: ponto fixo sobre os três domínios + post_step_update |
| `uml_editor.puml` | Classes | Camada gráfica: NodeItem, AnchorItem, ConnectionItem, LabelItem, EditorState |
| `uml_simulacao.puml` | Classes | Camada de simulação: SimulationSession, SimulationEngine, Node, Anchor |
| `uml_persistencia.puml` | Classes | Persistência e construção do grafo: SceneFileSession, Serializer, GraphBuilder |
| `casos_de_uso.puml` | Casos de uso | Interações do usuário agrupadas por contexto |

## Como gerar as imagens

Acesse [plantuml.com/plantuml](https://www.plantuml.com/plantuml), cole o conteúdo
do arquivo desejado e exporte como PDF ou SVG.

Alternativamente, com PlantUML instalado localmente:

```bash
plantuml -tpdf docs/diagramas/*.puml
```
