# Cómo funciona (para contarlo en una entrevista)

Escrito en castellano rioplatense, con los términos técnicos en inglés.
Lumen Goods es un retailer inventado. Los pedidos son sintéticos. No hay
datos de un cliente real.

La idea de este texto: que puedas explicar el sistema de punta a punta sin
leer el código en el momento. Si un número de abajo no dice "medido", es
[EST] o no es un número.

## En una frase

Es un agente de back-office que propone reembolsos, pero no mueve plata ni
manda un email hasta que una persona aprueba. Cada paso queda en una base.
Si el proceso se cae, retoma. Si alguien cambia el modelo y el agente se
salta un lookup, el CI no deja mergear.

## El problema, dicho simple

En la demo el agente "anda". El problema aparece después: cambian el prompt
o el modelo, el agente reembolsa de más o le escribe a otra persona, y se
enteran cuando el cliente se queja. No hay registro de qué hizo, ni un tope
de costo por corrida.

Eso es lo que este repo muestra cómo evitar, en chico.

## Qué hace cada módulo

Pensalo como cajas con una sola responsabilidad.

| Módulo | Qué hace | Qué no hace |
|---|---|---|
| `cli.py` / `api.py` | Arrancan una corrida, aprueban, rechazan, reanudan | No deciden la política |
| `demo.py` | Cuenta la historia: se cae, retoma, aprueba | Borra su propia base para que la historia se pueda repetir |
| `runner.py` | El loop. En cada vuelta hace una sola cosa | No esconde estado en memoria |
| `history.py` | Rearma el transcript leyendo los steps | No es otra fuente de verdad |
| `providers/fake.py` | El modelo local. Lee `customer_message` | No llama a la red |
| `providers/cassette.py` | Repite respuestas grabadas | No decide nada nuevo |
| `providers/openai_compatible.py` | POST HTTP al formato de OpenAI. Sirve para xAI u OpenAI | Apagado salvo `LIVE_MODE=1`. CI no lo usa. No está probado contra la API real |
| `providers/anthropic.py` | Adaptador fino al API Messages de Anthropic | Las mismas reglas: opt-in, tope de gasto, sin probar contra la API real |
| `tools.py` | Valida argumentos y ejecuta las cuatro tools | No aprueba |
| `gate.py` | La lista de tools que frenan: `send_refund`, `send_email` | No es un prompt |
| `policy.py` | La regla de negocio, pura: mismos datos, misma decisión | No toca la base |
| `catalog.py` | Los pedidos sintéticos, solo lectura | Los reembolsos no se escriben acá |
| `store.py` | SQLite: runs, steps, effects, ledger | No es Postgres |
| `trace.py` | Un JSONL por corrida: latencia, tokens, costo | No guarda el email ni el cuerpo |
| `evalkit/` | Los 23 casos, los cassettes, el checker determinístico | No llama a un modelo pago. `make eval-live` es aparte y no corre en CI |

## Las cuatro tools

1. `lookup_order` — lee un pedido. No frena.
2. `lookup_policy` — lee la ventana de días de un motivo. No frena.
3. `send_refund` — efecto externo. Frena hasta que una persona dice que sí.
4. `send_email` — efecto externo. Frena. El destinatario tiene que ser el
   email de ese pedido, en `@lumen-goods.example`.

No hay una tool `approve`. Si la hubiera, el modelo se aprobaría solo.

## Una corrida, de punta a punta

El ejemplo es el de `make demo`: pedido `LG-1001`, motivo `damaged`,
4200 centavos. La lámpara llegó rota. Todo es sintético.

1. El CLI crea una fila `runs` con estado `running` y el input en JSON.
2. El runner le pide un turno al provider. El stub no "piensa": mira qué
   tools ya se llamaron. Como no hubo lookup, pide `lookup_order`.
3. Ese turno se guarda como step. En la demo, ahí cortamos a propósito
   (`interrupted`). Es el crash entre dos pasos.
4. `resume` no vuelve a llamar al modelo para ese turno. Lee el step y
   sigue. Ejecuta `lookup_order`. El catálogo devuelve el pedido de Avery
   Chen. El email queda en la base, no en el trace.
5. El stub pide `lookup_policy`. La regla de `damaged` es 30 días. El
   pedido tiene 5. Sigue.
6. El stub pide `send_refund` por 4200, que es el saldo, no un número
   inventado. El runner valida los argumentos y, como la tool está en
   `gate.py`, inserta un step `waiting_review` y se detiene. Todavía no
   hay fila en `effects`. La plata no se movió.
7. Una persona aprueba por CLI o por la API. Eso no ejecuta todavía.
   `resume` ejecuta. `send_refund` vuelve a correr `policy.decide`. Si el
   monto no es el que la política permite, no escribe nada. Si coincide,
   escribe el effect y suma el ledger en la misma transacción.
8. El stub pide `send_email` al email del pedido. Otra vez el gate.
9. Después de la segunda aprobación, el stub cierra con un JSON chico:
   `outcome`, `order_id`, `amount_cents`, `customer_summary`. La corrida
   queda `completed`.

En la medición del 2026-10-18 (`make demo`, versión 0.1.0, modelo `stub-llm-v1`) esa
historia, con el corte y las dos aprobaciones, usó 3425 tokens de entrada,
124 de salida y 584 micro-USD al precio sintético. No es una factura de un
proveedor.

Si la persona rechaza el reembolso, el step queda `rejected`, el modelo
recibe ese resultado y el stub cierra en `refund_rejected`. El effect no
se escribe. El caso `edge_human_reject` acepta otra etiqueta, por ejemplo
`denied`, si no hubo effect, `send_refund` pasó por el gate, y el texto
al cliente no dice que el reembolso ya se hizo.

## Qué pasa si se cae a la mitad de la tool

El step queda `running` y el contador de intentos ya se guardó. Al retomar,
se reintenta con los intentos que quedan. Si el effect ya se había escrito,
la tool devuelve ese recibo y no suma de nuevo. Por eso el orden importa:
primero se busca el effect, después se revalida la política. Si lo hacés al
revés, el segundo intento ve el saldo en cero y parece un rechazo, aunque
la plata ya se movió.

## Por qué cada decisión

**El modelo no es de confianza.** El stub lee `customer_message`. Si el
texto pide saltear el lookup, inflar el monto, o mandar el mail a otra
dirección, el stub obedece. La tool o el gate lo frenan, y no queda un
effect. Eso prueba los controles contra este stub. No prueba un modelo
de verdad: el CI solo reproduce cassettes.

**El gate está en código, no en el prompt.** Un prompt que dice "no
reembolses sin aprobación" ayuda. Una rama que no ejecuta la tool hasta que
llega un approve por la API es más fuerte. El modelo no tiene cómo llamar
a ese approve.

**La idempotency key la calcula el runtime.** Si la elige el modelo, dos
reintentos pueden ser dos pagos. La key es tool + argumentos de negocio
(pedido, monto, motivo).

**SQLite ahora, Postgres después.** Para una demo y para el CI no hace
falta un servidor. Las tablas están pensadas para el diseño de producción:
un worker que toma una corrida con `SELECT … FOR UPDATE SKIP LOCKED` para
que dos workers no agarren la misma. Eso está escrito en el ADR 0001 y no
está implementado. No lo presentes como si ya corriera.

**Cassettes en el CI.** Una llamada live cuesta plata y no es
determinística. El CI reproduce las respuestas grabadas del stub. Las tools
y el gate sí corren de verdad. Grabar de nuevo es un diff que se revisa,
no un paso automático. Cambiar el modelo en producción, sin regrabar, no
pone el CI en rojo. El gate no ve ese cambio.

**Dos niveles de eval.** Lo determinístico (trayectoria, schema, montos,
effects, gate) bloquea siempre. El checker es una checklist en código y
bloquea si el puntaje baja de 0.80. No es un juez y no llama a un modelo.
Un LLM judge es trabajo futuro. No hay un número de acuerdo con humanos.
No lo inventes en la entrevista.

**Budget y circuit breaker son cosas distintas.** El budget es plata del
modelo (micro-USD). El tope del reembolso es otra cosa (el saldo del pedido
y un máximo de 100000 centavos). El circuit breaker cuenta fallos de tools
seguidos. Un turno del modelo que sale bien no lo reinicia, porque si no un
modelo que insiste con una tool rota lo resetearía siempre.

**Los traces no llevan el email.** Si mañana se exportan a un colector, no
querés una segunda pasada de redacción. El cuerpo y el destinatario quedan
en SQLite, que es el límite de confianza local.

## Cómo se lo explicaría a un cliente

En la primera reunión no abriría el repo. Diría esto:

"Hoy una persona lee el pedido, lee la política y tipea el reembolso.
Nosotros no sacamos a esa persona. El agente hace la lectura y propone el
monto. La persona aprueba o rechaza. Si el proceso se cae, no se paga dos
veces. Si mañana cambian el modelo, el mismo set de casos tiene que seguir
verde o el cambio no sale."

Después preguntaría las diez de [DISCOVERY.md](DISCOVERY.md), en este orden,
porque cambian el diseño:

- Si el error duele plata, hay gate. Si el agente solo redacta un texto que
  la persona siempre manda, el email ni es una tool.
- Si el sistema de registro no acepta una idempotency key, el piloto no
  arranca.
- Si el volumen es el de una oficina (en el caso hipotético, 120 por día
  [EST]), no arranco con una cola distribuida. Dejo escrito cuándo sí.
- Si no saben la tasa de error de hoy, no prometo una mejora. Mido "aprobado
  sin edición" en el piloto.
- Si el aprobador no tiene backup, no prendo el envío.

El rollout que propondría está en [SCOPE.md](SCOPE.md):

1. Sombra. El agente propone, la persona compara, no se envía nada. Salimos
   de la sombra con 30 borradores revisados a mano y ninguna violación de
   política. Eso es trabajo del piloto. Este repo no lo hizo.
2. Envío con gate. Recién ahí `send_refund` pega contra el sistema de ellos.
3. Recién después, más motivos de reembolso, de a uno, cada uno con casos
   nuevos en el golden set.

El handoff está en [RUNBOOK.md](RUNBOOK.md). El que construye no se queda
con el botón de aprobar. Operaciones opera. El aprobador aprueba. El que
cambia el prompt no se mergea solo.

Si me preguntan por el ahorro, separo los números. El costo del stub está
medido (584 micro-USD la demo, 12118 micro-USD las 27 corridas, el
2026-10-18). El ahorro de horas es [EST] y está en el business case, con
los supuestos a la vista. No mezclo las dos columnas.

## Casos de uso, gobernanza y estrategia

El README tiene una sección fija: "Use cases, governance and business
strategy". El detalle para adaptar el runtime está en
[ADAPT_TO_A_REAL_CLIENT.md](ADAPT_TO_A_REAL_CLIENT.md). En corto:

Este repo implementa un solo caso: el escritorio de reembolsos de Lumen
Desk. El agente propone. `send_refund` y `send_email` frenan hasta que una
persona aprueba o rechaza. `lookup_order` y `lookup_policy` solo leen. Si
el modelo dice que el reembolso ya se hizo y no hay un effect que coincida,
el runtime le devuelve el paso que falta (`completion_nudge`, tope
`MAX_COMPLETION_NUDGES`, 2) y no escribe el reembolso por su cuenta. Si
sigue diciéndolo, la corrida queda `failed` con `needs_review`. Ese detector es una lista de
frases en inglés y unas pocas en español (`reembolso procesado`, `ya te
devolvimos`, `se acreditó`). Es una heurística, no una garantía: otra
redacción o otro idioma no entra. Si la persona rechaza, como en
`edge_human_reject`, no se escribe ningún effect.

Los otros casos del README son bocetos, no código. Un agente de tickets
que clasifica y no avisa al cliente hasta que el dueño de la cola aprueba.
Un agente de turnos que no reserva, mueve ni cancela hasta que el dueño
del calendario dice que sí. Un asistente personal de gastos que propone un
pago y no mueve plata. Un asistente personal de correo que redacta y no
envía. En los cuatro, la persona aprueba el efecto. El modelo no tiene un
botón de aprobar. Ninguno nombra un cliente, un empleador ni un proyecto
real, y ninguno trae un volumen o un precio de verdad.

La gobernanza, en este repo, se señala con archivos:

- Controles: tools tipadas y privilegio mínimo en `tools.py`, tope de
  monto en `policy.py`.
- Gate humano: `gate.py`.
- Trazas: un JSONL por corrida en `trace.py`, con el run id, sin el cuerpo
  del email. Los casos adversariales chequean invariantes, no la lista
  exacta de tools del stub.
- Riesgos: [RISKS.md](RISKS.md).
- Costo y topes: [COST.md](COST.md).
- Incidente y rollback: [RUNBOOK.md](RUNBOOK.md).

No cubre el identity provider del cliente, OpenTelemetry, Postgres con
`SKIP LOCKED`, ni un juez de modelo.

La estrategia de negocio separa dos columnas. El ahorro de horas está en
[BUSINESS_CASE.md](BUSINESS_CASE.md) y es [EST] (unos USD 290 por día
hábil [EST], sobre 120 pedidos por día [EST]). El alcance y las fases,
con criterio de salida, están en [SCOPE.md](SCOPE.md): sombra, después
envío con gate, después más motivos de a uno. Lo medido está en
[METRICS.md](METRICS.md): el 2026-10-18 el stub pasó 27/27. Las métricas
de un cliente (aprobado sin editar, edad de la cola) están definidas y
vacías. En una conversación de Deployment Strategist el orden es sombra,
después gate, el que construye no se queda con el botón, y el CI prueba
el runtime.

## Preguntas que te pueden hacer

### De runtime

**¿Dónde está el estado si se cae el proceso?**
En SQLite. El runner no se acuerda de nada: en cada vuelta lee la corrida.
`interrupted` es un corte entre pasos. `running` en un step es un corte a
la mitad de la tool.

**¿Por qué no se paga dos veces?**
Porque la key de negocio ya está escrita. El segundo intento lee el effect
y devuelve el mismo recibo. El ledger no suma de nuevo.

**¿Qué pasa si el modelo se salta el lookup pero el monto es correcto?**
La tool rechaza `send_refund` si en esa corrida no hubo `lookup_order` y
`lookup_policy` exitosos. No abre el gate y no escribe un effect. El caso
`adv_skip_lookup` espera exactamente eso, y pasa. La regresión forzada
usa el mismo tipo de cassette contra el caso feliz, que espera un
reembolso completado, y por eso el gate queda rojo. Las dos cosas miden
distinto: una que el control frena el ataque, la otra que un transcript
malo no se cuela como caso feliz.

**¿El stub demuestra que GPT o Claude son seguros?**
No. Demuestra el runtime contra respuestas grabadas. Un modelo de verdad
no está en el CI. Regrabar cassettes sería un diff revisado, y hoy nadie
lo hace contra un modelo pago. Una corrida live, si la pagan, va aparte
y con tope.

**¿Por qué la latencia del stub es de microsegundos?**
Porque es el tiempo adentro del proceso, con un stub. No es un modelo en
red. El reporte separa las llamadas al modelo (`latency_us_p50` /
`latency_us_p95`) de los pasos de tools. En el stub las dos quedan en
microsegundos y no son un SLO. La latencia live de las llamadas al modelo,
en segundos, está en el README y es de tres corridas del 2026-10-18 en
`main` `3cbf6a7`, no una tasa de éxito.

### De Deployment Strategist

**¿Cómo lo ponés en producción sin arriesgar reembolsos?**
Sombra primero, gate después. Un solo motivo (`damaged`). Un aprobador con
backup. Cero effects sin una aprobación registrada es criterio de salida.
Si aparece uno, se apaga.

**¿Qué le pedís a IT del cliente?**
Un lugar donde correr el proceso, el secreto del modelo en el entorno (no
en el repo), un sistema de pedidos que acepte idempotency key, y el
identity provider delante de la API. Este MVP pide un bearer token
(`API_TOKEN`) en todo menos `GET /health`. Eso no reemplaza el login
del cliente.

**¿Quién es dueño del gate?**
El aprobador. El que cambia el prompt no aprueba los reembolsos de su
propio cambio el primer día. El backup está nombrado antes de prender el
envío. Después del handoff, el que construyó no conserva el botón.

**¿Cómo medís el piloto?**
En CI: el golden set verde y la regresión forzada roja. Con la gente: drafts
aprobados sin editar el monto, el motivo o el destinatario, y edad de la
cola. No publico un "accuracy" que no medí. No hay un acuerdo entre un
juez y un humano, porque no hay un juez: el checker es código.

**¿Qué pasa si cambian el modelo?**
El CI de este repo no se entera. Solo ve cassettes. Si quieren probar el
modelo nuevo, es una corrida aparte, con tope de gasto, y un diff de
cassettes que mira alguien que no lo escribió. La muestra live del
2026-10-18 está en el README: tres corridas, un modelo, no una tasa de
éxito. El CI sigue sin llamarla. `main` puede exigir el job `ci`. Ese check se
configura en GitHub. El repo no lo enciende solo. El rollback es deployar
la revisión anterior y rechazar lo que quedó esperando. Lo que ya se pagó
lo revierte una persona en el sistema de pedidos. El agente no tiene undo
mágico.

**¿Y si el cliente quiere sacarle el gate para ir más rápido?**
Les muestro el costo de un reembolso mal hecho contra el ahorro de los 45
segundos [EST]. Si igual lo quieren, queda fuera de este alcance. No es un
flag escondido.

**¿Cuánto cuesta?**
El camino por defecto, cero: stub y cassettes. Un modelo live no está en el
CI. El precio sintético del stub está en COST.md para que la cuenta cierre.
El precio de un proveedor se copia de la página oficial el día que se mide.
No tengo ese número porque no hice esa corrida.

**¿Qué no hace?**
Tiene un bearer token, no el identity provider del cliente. No exporta
OpenTelemetry. No corre dos workers con `SKIP LOCKED`. No tiene 100 casos.
No tiene un LLM judge. No promete un ROI medido. El business case marca
[EST] lo que es estimado.

**¿Cómo se lo dejás operando?**
Con el runbook: quién mira la cola, qué señal es un incidente, cómo se
retoma un step `running`, cómo se hace rollback, y un checklist de handoff.
La última línea es que el builder no se queda como aprobador.
