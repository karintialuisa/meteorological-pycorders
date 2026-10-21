# Template Power BI

Os PNGs sao fundos estaticos, nao relatorios PBIX. Os valores, filtros, graficos
e botoes devem ser criados como visuais nativos do Power BI sobre o fundo.
Nao ha dados ficticios embutidos nas imagens.

## Aplicar o fundo

1. Crie as paginas `Meteorologia` e `Qualidade da Agua`.
2. Em Exibir > Temas > Procurar temas, importe `tema_pycorders.json`.
3. Clique numa area vazia da pagina e abra Formatar pagina.
4. Em Configuracoes da tela (Canvas settings), escolha Personalizado:
   largura 1600 e altura 900.
5. Em Plano de fundo da tela (Canvas background), importe o PNG da pagina.
   Use ajuste Ajustar (Fit) e transparencia 0%. Nao use Papel de parede.
6. Use Exibir > Ajustar a pagina para trabalhar sem deformar o layout.

## Posicoes dos visuais

Em Formatar visual > Geral > Propriedades, informe X, Y, largura e altura.
Todos os numeros abaixo sao coordenadas no canvas de 1600 x 900.
Deixe os fundos dos visuais transparentes e desative bordas e sombras.
Os titulos ja estao no PNG; desative os titulos duplicados dos visuais.

| Visual | X | Y | Largura | Altura |
| --- | --- | --- | --- | --- |
| Filtro de estado | 240 | 156 | 320 | 40 |
| Filtro de cidade | 576 | 156 | 320 | 40 |
| Filtro de estacao | 912 | 156 | 320 | 40 |
| Filtro de periodo | 1248 | 156 | 320 | 40 |
| Valor do indicador 1 | 256 | 266 | 288 | 56 |
| Valor do indicador 2 | 592 | 266 | 288 | 56 |
| Valor do indicador 3 | 928 | 266 | 288 | 56 |
| Valor do indicador 4 | 1264 | 266 | 288 | 56 |
| Grafico esquerdo | 240 | 411 | 648 | 232 |
| Grafico direito | 920 | 411 | 648 | 232 |
| Tabela de leituras | 240 | 717 | 1328 | 126 |

Use segmentacoes do tipo lista suspensa para estado, cidade e estacao.
Se os controles da versao instalada nao couberem, aumente a altura e reduza
a fonte, sem sobrepor a faixa de indicadores. O periodo pode ser uma lista
suspensa de datas para caber na faixa; nao use um calendario expandido ali.
Os campos sao Estados[nome_estado], Cidades[nome_cidade],
Estacoes[nome_estacao] e a coluna Data da tabela de leituras da pagina.
Se Data ainda nao existir, duplique data_leitura no Power Query e converta
a copia para Data, preservando a coluna original. Defina previamente se a
analise usara UTC ou horario local e aplique o mesmo criterio as duas tabelas.

## Medidas de Meteorologia

Em Modelagem > Nova medida, crie cada medida separadamente:

```dax
Estacoes Meteo = DISTINCTCOUNT(Meteorologia[id_estacao])
```
```dax
Temperatura Ar Media = AVERAGE(Meteorologia[temperatura_ar])
```
```dax
Umidade Media = AVERAGE(Meteorologia[umidade])
```
```dax
Chuva Media = AVERAGE(Meteorologia[chuva])
```

Coloque essas medidas, nessa ordem, em quatro cartoes de valor unico.
Desative o rotulo da categoria; use fonte de 32 a 36 e unidades de exibicao
Nenhuma. Use zero casas decimais para contagem e uma para as medias.
Nao formate umidade como Porcentagem se os valores ja estiverem entre 0 e 100:
use numero decimal; o titulo do fundo ja informa %.

Nos graficos de linhas, use Data no eixo X (nao Hierarquia de data),
Temperatura Ar Media a esquerda e Umidade Media a direita. Ative tooltips.
Na tabela, use data_leitura, nome_estacao e as medicoes de meteorologia;
configure as medicoes como Nao resumir para exibir leituras individuais.
Pode incluir a chave da leitura para distinguir registros coincidentes.
Chuva Media representa a media das leituras selecionadas, nao precipitacao
total de uma cidade. Uma soma exige conhecer o intervalo de acumulacao do sensor.

## Medidas de Qualidade da Agua

```dax
Estacoes Agua = DISTINCTCOUNT(QualidadeAgua[id_estacao])
```
```dax
Temperatura Agua Media = AVERAGE(QualidadeAgua[temperatura_agua])
```
```dax
pH Medio = AVERAGE(QualidadeAgua[ph])
```
```dax
Oxigenio Medio = AVERAGE(QualidadeAgua[oxigenio])
```

Use essas quatro medidas nos cartoes. Nos graficos, use Data no eixo X,
pH Medio a esquerda e Oxigenio Medio a direita. Na tabela, use
id_leitura_origem, data_leitura, nome_estacao, temperatura_agua, ph,
oxigenio, condutividade e turbidez. Valores de pH medio sao apenas resumos
descritivos, nao uma medida de conformidade ou pH de mistura de amostras.
Confirme a unidade do oxigenio na origem antes de adiciona-la ao visual.

## Coluna lateral com nomes clicaveis

A coluna e uma barra de navegacao feita com botoes, nao uma coluna calculada.
Os nomes ja estao no fundo; os botoes serao areas transparentes sobre eles.

1. Em Inserir > Botoes > Em branco, insira um botao na pagina Meteorologia.
2. Em Geral > Propriedades, use X=12, Y=210, largura=184 e altura=48.
3. Desative texto, icone, preenchimento e borda do botao para deixar o nome
   Meteorologia do fundo visivel. Confira tambem os estados hover/pressionado.
4. Ative Acao, escolha Navegacao de pagina e destino Meteorologia.
5. Defina o tooltip como Ir para Meteorologia e o texto alternativo
   como Abrir pagina Meteorologia.
6. Duplique o botao. Mantenha X=12 e altere Y para 270.
7. No segundo botao, altere destino para Qualidade da Agua e ajuste tooltip
   e texto alternativo para esse destino.
8. Selecione os dois botoes, copie e cole na outra pagina.
9. No painel Selecao, renomeie os botoes e deixe-os a frente dos outros visuais.
10. Teste com Ctrl + clique no Desktop; no modo de leitura basta clicar.

O destaque da pagina atual ja muda entre os dois PNGs. A navegacao de pagina
nao aplica filtros por si so. Para manter estado, cidade e estacao ao trocar
de pagina, use Exibir > Sincronizar segmentacoes com os mesmos campos nas duas
paginas. Para sincronizar datas entre fatos, prefira uma dimensao calendario
comum relacionada a Data das duas tabelas; filtros baseados nas datas de fatos
diferentes nao devem ser tratados como uma unica segmentacao compartilhada.

## Atualizacao e manutencao

Atualize os Parquets e depois use Atualizar no Power BI. Os fundos nao contem
valores e nao precisam ser regenerados a cada carga. Para recriar os PNGs,
execute `./power_bi/Gerar_Fundos.ps1` no PowerShell. O gerador usa System.Drawing
do Windows e nao instala dependencias.