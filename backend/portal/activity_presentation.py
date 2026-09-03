from datetime import timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.utils import timezone


ACTIVITY_GROUP_WINDOW = timedelta(minutes=60)
ACTIVITY_RAW_LIMIT = 250
ACTIVITY_GROUP_LIMIT = 40


SUMMARY_RULES = {
    (
        "planificacion_obra",
        "crear_recurso_real_manual",
    ): (
        "registró",
        "un recurso real manual",
        "{cantidad} recursos reales manuales",
    ),
    (
        "planificacion_obra",
        "editar_recurso_real_manual",
    ): (
        "editó",
        "un recurso real manual",
        "{cantidad} recursos reales manuales",
    ),
    (
        "gestion",
        "crear_albaran",
    ): (
        "creó",
        "un albarán de proveedor",
        "{cantidad} albaranes de proveedor",
    ),
    (
        "gestion",
        "crear_factura",
    ): (
        "creó",
        "una factura de proveedor",
        "{cantidad} facturas de proveedor",
    ),
    (
        "archivos",
        "subida",
    ): (
        "subió",
        "un archivo",
        "{cantidad} archivos",
    ),
    (
        "archivos",
        "renombrar",
    ): (
        "renombró",
        "un elemento",
        "{cantidad} elementos",
    ),
    (
        "archivos",
        "crear_carpeta",
    ): (
        "creó",
        "una carpeta",
        "{cantidad} carpetas",
    ),
    (
        "archivos",
        "eliminar",
    ): (
        "eliminó",
        "un elemento",
        "{cantidad} elementos",
    ),
    (
        "agenda",
        "crear_evento",
    ): (
        "creó",
        "un evento",
        "{cantidad} eventos",
    ),
    (
        "agenda",
        "reprogramar_evento",
    ): (
        "reprogramó",
        "un evento",
        "{cantidad} eventos",
    ),
}


def _normalizar(value):
    return str(value or "").strip().lower()


def _entero_positivo(value):
    if value in (None, "", False):
        return 0

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return 0

    if number <= 0 or number != number.to_integral_value():
        return 0

    return int(number)


def nombre_familiar(user):
    if user is None:
        return "Sistema"

    first_name = str(
        getattr(user, "first_name", "") or ""
    ).strip()

    if first_name:
        return first_name

    try:
        username = str(
            user.get_username() or ""
        ).strip()
    except AttributeError:
        username = str(
            getattr(user, "username", "") or ""
        ).strip()

    if username:
        return username

    try:
        full_name = str(
            user.get_full_name() or ""
        ).strip()
    except AttributeError:
        full_name = ""

    return full_name or "Usuario"


def nombre_completo_usuario(user):
    if user is None:
        return "Sistema"

    try:
        full_name = str(
            user.get_full_name() or ""
        ).strip()
    except AttributeError:
        full_name = ""

    if full_name:
        return full_name

    try:
        username = str(
            user.get_username() or ""
        ).strip()
    except AttributeError:
        username = str(
            getattr(user, "username", "") or ""
        ).strip()

    return username or "Usuario"


def _cantidad_funcional(activity):
    metadata = (
        activity.metadata
        if isinstance(activity.metadata, dict)
        else {}
    )

    modulo = _normalizar(activity.modulo)
    accion = _normalizar(activity.accion)

    if (
        modulo == "planificacion_obra"
        and accion in {
            "crear_recurso_real_manual",
            "editar_recurso_real_manual",
        }
    ):
        cantidad = _entero_positivo(
            metadata.get("cantidad_registros")
        )

        if cantidad:
            return cantidad

        recursos = metadata.get("recursos")

        if isinstance(recursos, list) and recursos:
            return len(recursos)

        return 1

    if modulo == "archivos" and accion == "subida":
        cantidad = _entero_positivo(
            metadata.get("cantidad")
        )

        if cantidad:
            return cantidad

        nombres = metadata.get("nombres")

        if isinstance(nombres, list) and nombres:
            return len(nombres)

        archivo_ids = metadata.get("archivo_ids")

        if isinstance(archivo_ids, list) and archivo_ids:
            return len(archivo_ids)

        return 1

    if modulo == "gestion" and accion == "crear_albaran":
        return (
            _entero_positivo(
                metadata.get("albaranes_count")
            )
            or 1
        )

    return 1


def _frase_fallback(activity, cantidad):
    descripcion = str(
        activity.descripcion or ""
    ).strip()

    if cantidad == 1 and descripcion:
        if descripcion.lower().startswith("se "):
            descripcion = descripcion[3:]

        if descripcion:
            return (
                descripcion[0].lower()
                + descripcion[1:]
            )

    accion = (
        str(activity.accion or "actividad")
        .strip()
        .replace("_", " ")
    )

    if cantidad == 1:
        return f"realizó una acción de {accion}."

    return (
        f"realizó {cantidad} acciones de "
        f"{accion}."
    )


def _frase_resumen(group):
    rule = SUMMARY_RULES.get(
        (
            group.modulo_key,
            group.accion_key,
        )
    )

    if rule is None:
        return _frase_fallback(
            group.actividades[0],
            group.cantidad,
        )

    verbo, singular, plural = rule

    if group.cantidad == 1:
        complemento = singular
    else:
        complemento = plural.format(
            cantidad=group.cantidad
        )

    return f"{verbo} {complemento}."


def _clave_compatibilidad(activity):
    ocurrida_local = activity.ocurrida_local

    return (
        getattr(activity, "actor_id", None),
        getattr(activity, "team_id", None),
        _normalizar(activity.modulo),
        _normalizar(activity.accion),
        _normalizar(activity.tipo_objeto),
        _normalizar(activity.visibilidad),
        _normalizar(activity.origen),
        ocurrida_local.date(),
    )


def _nuevo_grupo(activity):
    ocurrida_local = activity.ocurrida_local

    return SimpleNamespace(
        actor=activity.actor,
        actor_nombre=nombre_familiar(
            activity.actor
        ),
        actor_nombre_completo=(
            nombre_completo_usuario(
                activity.actor
            )
        ),
        team=activity.team,
        modulo_key=activity.modulo_key,
        modulo_label=activity.modulo_label,
        modulo_icon=activity.modulo_icon,
        modulo_badge_class=(
            activity.modulo_badge_class
        ),
        accion_key=_normalizar(
            activity.accion
        ),
        tipo_objeto_key=_normalizar(
            activity.tipo_objeto
        ),
        ocurrida_local=ocurrida_local,
        inicio_local=ocurrida_local,
        fin_local=ocurrida_local,
        actividades=[activity],
        cantidad=_cantidad_funcional(
            activity
        ),
        pk=activity.pk,
        id=activity.id,
        url=activity.url,
        objeto_repr=activity.objeto_repr,
        detalle_nombres=[],
        detalle_restantes=0,
        descripcion="",
        horario_label="",
    )


def _incorporar(group, activity):
    group.actividades.append(activity)
    group.cantidad += _cantidad_funcional(
        activity
    )

    if activity.ocurrida_local < group.inicio_local:
        group.inicio_local = (
            activity.ocurrida_local
        )

    if activity.ocurrida_local > group.fin_local:
        group.fin_local = (
            activity.ocurrida_local
        )
        group.ocurrida_local = (
            activity.ocurrida_local
        )


def _finalizar_grupo(group):
    group.actividades.sort(
        key=lambda item: (
            item.ocurrida_local,
            item.id or 0,
        ),
        reverse=True,
    )

    nombres = []

    for activity in group.actividades:
        for nombre in getattr(
            activity,
            "detalle_nombres",
            [],
        ):
            clean = str(nombre or "").strip()

            if clean and clean not in nombres:
                nombres.append(clean)

    group.detalle_nombres = nombres[:3]

    if group.modulo_key == "archivos":
        group.detalle_restantes = max(
            group.cantidad
            - len(group.detalle_nombres),
            0,
        )

    if len(group.actividades) != 1:
        group.url = ""
        group.objeto_repr = ""

    if group.inicio_local == group.fin_local:
        group.horario_label = (
            group.fin_local.strftime("%H:%M")
        )
    else:
        group.horario_label = (
            f"{group.inicio_local:%H:%M}"
            f"–{group.fin_local:%H:%M}"
        )

    group.descripcion = _frase_resumen(
        group
    )

    return group


def compactar_actividades(
    actividades,
    *,
    ventana=ACTIVITY_GROUP_WINDOW,
):
    grupos = []
    grupo_actual_por_clave = {}

    ordered = sorted(
        actividades,
        key=lambda item: (
            item.ocurrida_local,
            item.id or 0,
        ),
        reverse=True,
    )

    for activity in ordered:
        key = _clave_compatibilidad(
            activity
        )

        group = grupo_actual_por_clave.get(
            key
        )

        if (
            group is None
            or (
                group.fin_local
                - activity.ocurrida_local
            ) > ventana
        ):
            group = _nuevo_grupo(
                activity
            )
            grupos.append(group)
            grupo_actual_por_clave[key] = group
        else:
            _incorporar(
                group,
                activity,
            )

    grupos = [
        _finalizar_grupo(group)
        for group in grupos
    ]

    grupos.sort(
        key=lambda group: (
            group.fin_local,
            group.id or 0,
        ),
        reverse=True,
    )

    return grupos
