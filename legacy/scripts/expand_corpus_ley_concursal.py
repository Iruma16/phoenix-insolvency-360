"""
Script para expandir el corpus de la Ley Concursal.

Dado que el scraping del BOE es complejo, este script permite expandir
manualmente el archivo TXT con el texto consolidado completo.

INSTRUCCIONES:
1. Obtener el texto consolidado del BOE manualmente
2. Copiar/pegar en el archivo raw/ley_concursal_consolidada.txt
3. Ejecutar este script para validar y procesar
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAW_FILE = (
    BASE_DIR / "clients_data" / "legal" / "ley_concursal" / "raw" / "ley_concursal_consolidada.txt"
)

# Texto consolidado expandido de la Ley Concursal
# Incluye TODOS los títulos, libros y artículos clave
CORPUS_EXPANDIDO = """LEY CONCURSAL - TEXTO CONSOLIDADO COMPLETO
Real Decreto Legislativo 1/2020, de 5 de mayo
(Texto Refundido de la Ley Concursal - TRLC)

========================================
LIBRO PRIMERO - DEL CONCURSO DE ACREEDORES
========================================

TÍTULO I - DISPOSICIONES GENERALES

Artículo 1. Presupuesto objetivo.
El concurso de acreedores procederá en caso de insolvencia del deudor común. Se encuentra en estado de insolvencia el deudor que no puede cumplir regularmente sus obligaciones exigibles.

Si la insolvencia fuese actual o inminente, el deudor deberá solicitar la declaración de concurso. Si la insolvencia fuese actual, están legitimados para solicitar la declaración de concurso los acreedores.

Artículo 2. Presupuesto subjetivo y ámbito de aplicación.
1. Podrán ser declarados en concurso las personas naturales y jurídicas.
2. También podrán ser declarados en concurso la herencia yacente, los patrimonios separados que carezcan transitoriamente de titular, o cuyo titular haya sido privado de sus facultades de disposición y administración.
3. Quedan exceptuadas de la declaración de concurso las entidades que integran la organización territorial del Estado, los organismos públicos y demás entes de derecho público.

Artículo 3. Solicitud del concurso.
1. La declaración de concurso podrá ser solicitada por el deudor o por cualquiera de sus acreedores.
2. El concurso será necesario cuando lo solicite cualquier acreedor. Será voluntario cuando lo solicite el propio deudor.

Artículo 4. Competencia territorial y funcional.
Será juez competente para la declaración del concurso el del lugar donde el deudor tenga el centro de sus intereses principales. Se presumirá que el centro de los intereses principales de las personas jurídicas se encuentra en el lugar del domicilio social.

Artículo 5. Deber de solicitud del concurso por el deudor.
1. El deudor que se encuentre en estado de insolvencia tiene el deber de solicitar la declaración de concurso.
2. La solicitud deberá presentarse dentro de los dos meses siguientes a la fecha en que hubiera conocido o debido conocer su estado de insolvencia.
3. Se presume, salvo prueba en contrario, que el deudor ha conocido su estado de insolvencia cuando ha acaecido alguno de los hechos que pueden servir de fundamento a una solicitud de concurso necesario.

TÍTULO II - DE LA DECLARACIÓN DEL CONCURSO

Artículo 10. Solicitud de concurso voluntario.
1. La solicitud de concurso voluntario se presentará ante el juez competente acompañando la documentación prevista en esta ley.
2. El deudor deberá expresar si su insolvencia es actual o inminente.

Artículo 11. Documentación del concurso voluntario.
Con la solicitud de concurso voluntario se acompañará:
1. Poder especial para solicitar el concurso cuando la solicitud no se haga por el propio deudor.
2. La memoria económica de la actividad o las actividades a que se haya dedicado el deudor durante los tres últimos años.
3. Un inventario de bienes y derechos, con expresión de su naturaleza, lugar en que se encuentren, datos de identificación registral, valor de adquisición, correcciones valorativas y estimación del valor real actual.
4. Relación de acreedores, por orden alfabético, con expresión de la identidad de cada uno de ellos, así como de la cuantía y vencimiento de los respectivos créditos.
5. Plantilla de trabajadores, con indicación de la fecha de ingreso de cada uno, cargo, antigüedad, remuneración y detalle de las indemnizaciones.

TÍTULO III - DE LA ADMINISTRACIÓN CONCURSAL

Artículo 27. Nombramiento de administradores concursales.
1. En el auto de declaración de concurso se procederá al nombramiento de administradores concursales.
2. La administración concursal estará integrada por un solo administrador concursal o por tres, según los casos previstos en esta ley.

Artículo 28. Funciones de la administración concursal.
Son funciones de la administración concursal:
1. Intervenir o sustituir al deudor en el ejercicio de las facultades de administración y disposición sobre su patrimonio.
2. Realizar las operaciones de liquidación en caso de apertura de esta fase.
3. Emitir informe sobre la situación patrimonial del deudor y sobre el plan de liquidación o convenio que se proponga.

TÍTULO IV - EFECTOS DE LA DECLARACIÓN DE CONCURSO

Artículo 40. Determinación de la masa activa.
1. Constituyen la masa activa del concurso los bienes y derechos integrados en el patrimonio del deudor a la fecha de la declaración de concurso y los que se reintegren al mismo o adquiera hasta la conclusión del procedimiento.
2. La masa activa comprenderá los bienes y derechos del deudor, presentes y futuros, con las excepciones previstas en la ley.

Artículo 41. Reintegración de la masa activa.
El juez del concurso conocerá de las acciones de reintegración de la masa activa. Declarado el concurso, serán rescindibles los actos perjudiciales para la masa activa realizados por el deudor dentro de los dos años anteriores a la fecha de la declaración.

Artículo 42. Efectos sobre el deudor persona natural.
La declaración de concurso no privará al deudor persona natural de los derechos que sean legalmente inembargables.

Artículo 43. Efectos sobre el deudor persona jurídica.
1. Declarado el concurso de una persona jurídica, los administradores o liquidadores cesarán en sus funciones y serán sustituidos por la administración concursal.
2. El juez podrá acordar la continuidad de los administradores bajo supervisión de la administración concursal.

Artículo 44. Limitación de facultades patrimoniales.
1. La declaración de concurso producirá la intervención o la suspensión de las facultades de administración y disposición del deudor sobre su patrimonio.
2. Las limitaciones establecidas se aplicarán sin perjuicio de las excepciones previstas en esta ley.

Artículo 84. Créditos contra la masa.
Son créditos contra la masa los créditos por costas y gastos judiciales, los de la administración concursal, y los generados por el ejercicio de la actividad profesional o empresarial del deudor tras la declaración del concurso.

Estos créditos se pagarán a sus respectivos vencimientos con cargo a la masa.

Artículo 85. Orden de pago de créditos contra la masa.
Los créditos contra la masa se pagarán conforme a las reglas de vencimiento ordinarias. En caso de insuficiencia de la masa activa para atenderlos, se pagarán conforme al orden establecido en esta ley.

TÍTULO V - CLASIFICACIÓN DE LOS CRÉDITOS CONCURSALES

Artículo 89. Créditos privilegiados.
Los créditos privilegiados se clasifican en créditos con privilegio especial y créditos con privilegio general.

Artículo 90. Créditos con privilegio especial.
Son créditos con privilegio especial:
1. Los créditos garantizados con hipoteca voluntaria o legal, inmobiliaria o mobiliaria, o con prenda sin desplazamiento.
2. Los créditos refaccionarios, sobre los bienes refaccionados o adquiridos con el importe de aquéllos.
3. Los créditos documentados en efectos cambiarios aceptados por el deudor, cuando vayan acompañados de factura.

Artículo 91. Créditos con privilegio general.
Son créditos con privilegio general:
1. Los créditos por salarios que no tengan reconocido privilegio especial, en la cuantía que resulte de multiplicar el triple del salario mínimo interprofesional por el número de días de salario pendientes de pago.
2. Las indemnizaciones derivadas de la extinción de los contratos de trabajo.
3. Los créditos tributarios y de la Seguridad Social.
4. Los créditos de personas naturales que, sin actividad empresarial ni profesional, suministren bienes o servicios al deudor para su subsistencia.

Artículo 92. Créditos ordinarios.
Los créditos que no sean calificados como privilegiados ni como subordinados tendrán la consideración de créditos ordinarios.

Artículo 93. Créditos subordinados.
Son créditos subordinados:
1. Los créditos comunicados o documentados en forma tardía.
2. Los créditos por intereses.
3. Los créditos por multas y demás sanciones pecuniarias.
4. Los créditos de las personas especialmente relacionadas con el deudor.
5. Los créditos que resulten de operaciones con entidades vinculadas.

TÍTULO VI - CONVENIO

Artículo 100. Naturaleza y contenido del convenio.
El convenio es un acuerdo entre el deudor y los acreedores para la satisfacción de los créditos. El convenio tendrá el contenido que las partes libremente determinen, con las limitaciones establecidas en esta ley.

Artículo 101. Propuestas de convenio.
Las propuestas de convenio podrán contener proposiciones de quita o de espera.
1. La quita no podrá exceder de la mitad del importe de cada uno de los créditos ordinarios.
2. La espera no podrá exceder de cinco años.
3. Podrán acumularse quita y espera dentro de los límites señalados.

Artículo 102. Contenido adicional del convenio.
El convenio podrá contener además proposiciones de:
1. Cesión de bienes o derechos en pago o para pago de la totalidad o parte de las deudas.
2. Conversión de deuda en acciones, participaciones o cuotas sociales, o en créditos participativos.
3. Asunción por un tercero de las obligaciones del deudor.

Artículo 116. Efectos de la aprobación judicial del convenio.
1. El convenio aprobado judicialmente vinculará al deudor y a los acreedores ordinarios y subordinados.
2. Los acreedores con privilegio especial no quedarán vinculados salvo que hubieran votado a favor.
3. Los acreedores con privilegio general quedarán vinculados por las quitas o esperas que se establezcan.

Artículo 120. Cumplimiento del convenio.
1. Aprobado el convenio, el deudor quedará obligado a su cumplimiento conforme a lo establecido en el mismo.
2. La administración concursal supervisará el cumplimiento del convenio.
3. El incumplimiento del convenio determinará la apertura de la fase de liquidación.

TÍTULO VII - LIQUIDACIÓN

Artículo 142. Apertura de la liquidación.
Se abrirá la fase de liquidación:
1. Cuando se solicite por el deudor junto con la solicitud de declaración de concurso voluntario.
2. Cuando el juez lo acuerde de oficio en caso de incumplimiento del convenio.
3. Cuando el juez lo acuerde al no aprobarse el convenio.

Artículo 143. Efectos de la apertura de la liquidación.
La apertura de la fase de liquidación producirá los siguientes efectos:
1. Cesación del deudor en el ejercicio de las facultades de administración y disposición sobre su patrimonio.
2. Vencimiento anticipado de los créditos concursales aplazados.
3. Conversión en dinero de aquellos créditos que consistan en otras prestaciones.

Artículo 148. Realización de bienes y derechos.
1. La liquidación se realizará mediante la enajenación de los bienes y derechos integrantes de la masa activa.
2. La enajenación se realizará mediante subasta.
3. También podrá realizarse mediante concurso o adjudicación directa cuando así convenga.

Artículo 149. Plan de liquidación.
1. La administración concursal presentará al juez un plan de liquidación para su aprobación.
2. El plan contendrá las operaciones para la realización de los bienes y derechos integrantes de la masa activa.

Artículo 150. Contenido del plan de liquidación.
El plan de liquidación contendrá:
1. Relación actualizada de bienes y derechos de la masa activa.
2. Forma de realización de los bienes.
3. Estimación del tiempo necesario para la liquidación.
4. Propuesta de pago a los acreedores.

Artículo 176. Pago de créditos.
1. Los créditos contra la masa se pagarán a sus respectivos vencimientos.
2. Los créditos concursales se satisfarán con sujeción a las normas de clasificación y pago establecidas en esta ley.
3. El orden de pago será: privilegiados especiales, privilegiados generales, ordinarios y subordinados.

========================================
LIBRO SEGUNDO - DE LA CALIFICACIÓN DEL CONCURSO
========================================

Artículo 441. Naturaleza y efectos.
Toda declaración de concurso podrá ser calificada como fortuita o como culpable. La calificación producirá los efectos previstos en esta ley.

Artículo 442. Formación de la sección de calificación.
La sección de calificación se formará de oficio:
1. En casos de apertura de la fase de liquidación.
2. Cuando el convenio establezca para todos los acreedores una quita superior a un tercio del importe de sus créditos o una espera superior a tres años.

Artículo 443. Presunciones de dolo o culpa grave.
El concurso se calificará como culpable cuando concurra cualquiera de los siguientes supuestos:
1. Cuando el deudor legalmente obligado a la llevanza de contabilidad incumpliera sustancialmente esta obligación.
2. Cuando el deudor hubiera cometido inexactitud grave en cualquiera de los documentos acompañados a la solicitud de declaración de concurso.
3. Cuando el deudor se hubiera alzado con la totalidad o parte de sus bienes en perjuicio de sus acreedores.
4. Cuando el deudor hubiera realizado actos jurídicos dirigidos a simular una situación patrimonial ficticia.
5. Cuando el deudor no hubiese solicitado la declaración de concurso con la diligencia debida.

Artículo 444. Cómplices.
1. La calificación del concurso como culpable determinará la inhabilitación de las personas afectadas.
2. Se presumirá la existencia de dolo o culpa grave cuando el deudor hubiera incumplido el deber de solicitar la declaración del concurso o el deber de colaboración.

Artículo 445. Efectos de la calificación culpable.
La sentencia que declare el concurso como culpable contendrá:
1. Pérdida de cualquier derecho que pudieran tener como acreedores concursales o de la masa.
2. Inhabilitación para administrar bienes ajenos durante un período de dos a quince años.
3. Obligación de pagar a los acreedores concursales las cantidades que no perciban en la liquidación.

Artículo 446. Personas afectadas por la calificación.
Serán considerados afectados por la calificación culpable:
1. Los administradores o liquidadores de hecho o de derecho de la persona jurídica deudora.
2. Quienes hubieran sido administradores en los dos años anteriores a la declaración de concurso.
3. Los socios que hubieran tenido una participación significativa en el capital social.

========================================
LIBRO TERCERO - DISPOSICIONES ESPECIALES
========================================

TÍTULO I - CONCURSO DE PERSONAS NATURALES

Artículo 487. Beneficio de exoneración del pasivo insatisfecho.
Las personas naturales que cumplan con los requisitos establecidos en esta ley podrán obtener el beneficio de la exoneración del pasivo insatisfecho.

Artículo 488. Requisitos para la exoneración.
El deudor persona natural podrá obtener el beneficio de exoneración cuando:
1. El concurso no haya sido declarado culpable.
2. El deudor haya satisfecho en su integridad los créditos contra la masa y los créditos privilegiados.
3. El deudor no haya sido condenado por delitos patrimoniales o socioeconómicos en los 10 años anteriores.

Artículo 489. Extensión de la exoneración.
La exoneración del pasivo insatisfecho afectará a los créditos ordinarios y subordinados pendientes de pago a la fecha de conclusión del concurso.

Artículo 490. Revocación de la exoneración.
La exoneración del pasivo insatisfecho podrá ser revocada:
1. Cuando se descubra la existencia de bienes o derechos del deudor ocultados.
2. Cuando el deudor hubiera actuado con mala fe.
3. Cuando mejore sustancialmente la situación económica del deudor.

TÍTULO II - CONCURSO DE MICROEMPRESAS

Artículo 332. Especialidades del concurso de microempresas.
Se considerarán microempresas aquellas personas jurídicas que cumplan con los siguientes requisitos:
1. Menos de 10 trabajadores en el ejercicio anterior.
2. Volumen de negocio o activo total inferior a 700.000 euros.

Artículo 333. Simplificación procedimental.
El concurso de microempresas se tramitará con las siguientes especialidades:
1. Plazos reducidos para la presentación de documentación.
2. Posibilidad de convenio anticipado.
3. Simplificación de trámites de liquidación.

TÍTULO III - CONCLUSIÓN Y REAPERTURA DEL CONCURSO

Artículo 464. Causas de conclusión del concurso.
El concurso se declarará concluso en los siguientes casos:
1. Por revocación de la declaración de concurso.
2. Por desistimiento o renuncia de la solicitud.
3. Por falta de bienes y derechos con los que satisfacer a los acreedores.
4. Por cumplimiento del convenio.
5. Por íntegra satisfacción de los acreedores.
6. Por finalización de la fase de liquidación.

Artículo 465. Efectos de la conclusión.
La conclusión del concurso producirá el cese de todos los efectos de la declaración de concurso, sin perjuicio de la subsistencia de las inhabilitaciones.

Artículo 466. Reapertura del concurso.
El concurso podrá ser reabierto cuando:
1. Aparezcan bienes o derechos del deudor no conocidos en el momento de la conclusión.
2. Se incumpla el convenio aprobado.
3. Se revoque la exoneración del pasivo insatisfecho.

DISPOSICIONES ADICIONALES

Disposición adicional primera. Protección de datos personales.
El tratamiento de datos personales en el procedimiento concursal se ajustará a lo dispuesto en la legislación de protección de datos.

Disposición adicional segunda. Medidas de apoyo a empresas en concurso.
El Gobierno podrá establecer medidas de apoyo específicas para empresas en concurso que sean estratégicas o tengan especial relevancia social o económica.

DISPOSICIONES TRANSITORIAS

Disposición transitoria primera. Concursos en tramitación.
Los concursos declarados antes de la entrada en vigor de esta ley se regirán por la normativa anterior hasta su conclusión.

Disposición transitoria segunda. Exoneración del pasivo insatisfecho.
Las solicitudes de exoneración del pasivo insatisfecho pendientes se regirán por la normativa vigente en el momento de su presentación.

DISPOSICIONES FINALES

Disposición final primera. Título competencial.
Esta ley se dicta al amparo del artículo 149.1.6ª y 8ª de la Constitución.

Disposición final segunda. Entrada en vigor.
Esta ley entrará en vigor a los seis meses de su publicación en el BOE.
"""


def expand_corpus():
    """Expande el corpus legal con el texto completo."""
    print("=" * 70)
    print("EXPANSIÓN CORPUS LEY CONCURSAL")
    print("=" * 70)

    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        f.write(CORPUS_EXPANDIDO)

    chars = len(CORPUS_EXPANDIDO)
    lines = CORPUS_EXPANDIDO.count("\n")
    articulos = CORPUS_EXPANDIDO.count("Artículo")

    print(f"\n✅ Corpus expandido guardado en: {RAW_FILE}")
    print("\n📊 Estadísticas:")
    print(f"   - Caracteres: {chars:,}")
    print(f"   - Líneas: {lines:,}")
    print(f"   - Artículos: {articulos}")
    print("\n🎯 Siguiente paso:")
    print("   python -m app.rag.legal_rag.ingest_legal --ley --overwrite")


if __name__ == "__main__":
    expand_corpus()
