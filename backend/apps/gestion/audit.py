# GESTION_TRAZABILIDAD_V1
import threading

from django.db import OperationalError, ProgrammingError
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

_thread_locals = threading.local()


def set_current_user(user):
    _thread_locals.user = user


def get_current_user():
    user = getattr(_thread_locals, "user", None)
    if getattr(user, "is_authenticated", False):
        return user
    return None


class GestionAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)


def _safe_raw_data(instance):
    raw = getattr(instance, "raw_data", None)
    return raw if isinstance(raw, dict) else {}


def _infer_origen(instance, created=False):
    raw = _safe_raw_data(instance)
    source = " ".join([
        str(raw.get("created_from", "")),
        str(raw.get("updated_from", "")),
        str(raw.get("source", "")),
        str(raw.get("origen", "")),
    ]).lower()

    if "ocr" in source or "pdf" in source:
        return "PDF_OCR"
    if "sync" in source or "access" in source or "legacy" in source:
        return "SYNC_ACCESS"
    if created:
        return "MANUAL"
    return getattr(instance, "origen_alta", "") or "LEGACY"


def _repr_obj(instance):
    for attrs in [
        ("cod_albaran", "num_albaran_proveedor"),
        ("cod_factura", "num_factura_proveedor"),
        ("linea",),
        ("nombre_original",),
    ]:
        values = []
        for attr in attrs:
            if hasattr(instance, attr):
                value = getattr(instance, attr, None)
                if value not in [None, ""]:
                    values.append(str(value))
        if values:
            return " / ".join(values)
    return str(instance)


def _get_team(instance):
    if hasattr(instance, "team_id"):
        return getattr(instance, "team", None)
    if hasattr(instance, "albaran_id") and getattr(instance, "albaran_id", None):
        return getattr(instance.albaran, "team", None)
    if hasattr(instance, "factura_id") and getattr(instance, "factura_id", None):
        return getattr(instance.factura, "team", None)
    return None


def _get_albaran(instance):
    if instance.__class__.__name__ == "AlbaranProveedorGestion":
        return instance
    if hasattr(instance, "albaran_id") and getattr(instance, "albaran_id", None):
        return getattr(instance, "albaran", None)
    return None


def _get_factura(instance):
    if instance.__class__.__name__ == "FacturaProveedorGestion":
        return instance
    if hasattr(instance, "factura_id") and getattr(instance, "factura_id", None):
        return getattr(instance, "factura", None)
    return None


def _accion_for(instance, created):
    name = instance.__class__.__name__
    if name == "DocumentoCompraAdjunto" and created:
        return "PDF_SUBIDO"
    if name == "FacturaAlbaranGestion" and created:
        return "VINCULO_CREADO"
    return "CREADO" if created else "MODIFICADO"


def _descripcion_for(instance, created):
    name = instance.__class__.__name__
    if name == "DocumentoCompraAdjunto" and created:
        return f"PDF adjunto subido: {getattr(instance, 'nombre_original', '')}"
    if name == "FacturaAlbaranGestion" and created:
        return "Vínculo factura-albarán creado"
    return f"{'Creado' if created else 'Modificado'} {name}: {_repr_obj(instance)}"


def _write_audit(instance, created):
    from apps.gestion.models import GestionAuditLog

    user = get_current_user()
    if instance.__class__.__name__ == "DocumentoCompraAdjunto":
        user = getattr(instance, "subido_por", None) or user

    try:
        GestionAuditLog.objects.create(
            team=_get_team(instance),
            usuario=user,
            accion=_accion_for(instance, created),
            entidad=instance.__class__.__name__,
            objeto_id=getattr(instance, "pk", None),
            objeto_repr=_repr_obj(instance)[:255],
            albaran=_get_albaran(instance),
            factura=_get_factura(instance),
            adjunto=instance if instance.__class__.__name__ == "DocumentoCompraAdjunto" else None,
            descripcion=_descripcion_for(instance, created),
            metadata={
                "created": created,
                "origen_alta": getattr(instance, "origen_alta", ""),
                "raw_created_from": _safe_raw_data(instance).get("created_from", ""),
                "raw_updated_from": _safe_raw_data(instance).get("updated_from", ""),
            },
        )
    except (OperationalError, ProgrammingError):
        pass
    except Exception:
        # La auditoría no debe romper operaciones de gestión.
        pass


TRACE_MODELS = {
    "AlbaranProveedorGestion",
    "FacturaProveedorGestion",
    "AlbaranProveedorLineaGestion",
    "FacturaProveedorLineaGestion",
    "FacturaAlbaranGestion",
    "DocumentoCompraAdjunto",
}


@receiver(pre_save)
def gestion_trace_pre_save(sender, instance, **kwargs):
    if sender.__name__ not in TRACE_MODELS:
        return

    user = get_current_user()

    if hasattr(instance, "creado_por_id") and not getattr(instance, "creado_por_id", None) and user:
        instance.creado_por = user

    if hasattr(instance, "modificado_por_id") and user:
        instance.modificado_por = user

    if hasattr(instance, "origen_alta"):
        created = getattr(instance, "pk", None) is None
        current = getattr(instance, "origen_alta", "") or ""
        if not current or current == "LEGACY":
            instance.origen_alta = _infer_origen(instance, created=created)


@receiver(post_save)
def gestion_trace_post_save(sender, instance, created, raw=False, **kwargs):
    if raw or sender.__name__ not in TRACE_MODELS:
        return
    _write_audit(instance, created)


@receiver(post_delete)
def gestion_trace_post_delete(sender, instance, **kwargs):
    if sender.__name__ not in TRACE_MODELS:
        return

    from apps.gestion.models import GestionAuditLog

    try:
        GestionAuditLog.objects.create(
            team=_get_team(instance),
            usuario=get_current_user(),
            accion="ELIMINADO",
            entidad=instance.__class__.__name__,
            objeto_id=getattr(instance, "pk", None),
            objeto_repr=_repr_obj(instance)[:255],
            albaran=_get_albaran(instance),
            factura=_get_factura(instance),
            descripcion=f"Eliminado {instance.__class__.__name__}: {_repr_obj(instance)}",
            metadata={},
        )
    except Exception:
        pass

# GESTION_AMBITO_OBRA_DEFAULT_V1
# Regla funcional: facturas/albaranes de compra son OBRA por defecto.
# El centro de coste se asigna automáticamente a OBRA_SIN_ASIGNAR si no viene uno concreto.
from django.db.models.signals import pre_save
from django.dispatch import receiver

def _gestion_get_centro_obra_default_v1(instance):
    try:
        from apps.gestion.models import CentroCosteGestion
    except Exception:
        return None

    team = getattr(instance, "team", None)
    if not team:
        return None

    obra = getattr(instance, "obra_planificacion", None)
    if obra:
        centro = (
            CentroCosteGestion.objects
            .filter(team=team, tipo="OBRA", obra_planificacion=obra, activo=True)
            .first()
        )
        if centro:
            return centro

    return (
        CentroCosteGestion.objects
        .filter(team=team, codigo="OBRA_SIN_ASIGNAR", activo=True)
        .first()
    )

def _gestion_set_ambito_obra_default_v1(instance):
    # Solo fuerza OBRA cuando viene vacío o aún está SIN_CLASIFICAR.
    # Si en el futuro se marca ADMINISTRACION/VEHICULOS/etc., no lo pisa.
    ambito = (getattr(instance, "ambito_gestion", "") or "").strip()
    if not ambito or ambito == "SIN_CLASIFICAR":
        instance.ambito_gestion = "OBRA"

    if getattr(instance, "ambito_gestion", None) == "OBRA" and not getattr(instance, "centro_coste_id", None):
        centro = _gestion_get_centro_obra_default_v1(instance)
        if centro:
            instance.centro_coste = centro

try:
    from apps.gestion.models import AlbaranProveedorGestion, FacturaProveedorGestion

    @receiver(pre_save, sender=AlbaranProveedorGestion)
    def _gestion_albaran_ambito_obra_default_v1(sender, instance, **kwargs):
        _gestion_set_ambito_obra_default_v1(instance)

    @receiver(pre_save, sender=FacturaProveedorGestion)
    def _gestion_factura_ambito_obra_default_v1(sender, instance, **kwargs):
        _gestion_set_ambito_obra_default_v1(instance)

except Exception:
    # Evita romper arranque en contextos de migración temprana.
    pass


# GESTION_CENTRO_COSTE_AUTO_POR_AMBITO_PROVEEDOR_V2
def _gestion_legacy_to_int_v2(value):
    if value in (None, ""):
        return None
    s = str(value).strip()
    if not s or s in {"0", "-", "None", "none", "NULL", "null"}:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _gestion_find_obra_by_legacy_v2(team, legacy_value):
    legacy = _gestion_legacy_to_int_v2(legacy_value)
    if not team or not legacy:
        return None
    try:
        from apps.planificacion_obra.models import ObraPlanificacion
    except Exception:
        return None
    return ObraPlanificacion.objects.filter(team=team, legacy_cod_obra=legacy).first()


def _gestion_resolve_centro_coste_auto_v2(instance):
    try:
        from apps.gestion.models import CentroCosteGestion
    except Exception:
        return None

    team = getattr(instance, "team", None)
    if not team:
        return None

    ambito = (getattr(instance, "ambito_gestion", "") or "").strip() or "OBRA"
    if ambito == "SIN_CLASIFICAR":
        ambito = "OBRA"

    instance.ambito_gestion = ambito

    if ambito != "OBRA":
        instance.obra_planificacion = None
        centro = CentroCosteGestion.objects.filter(team=team, codigo=ambito, activo=True).first()
        if centro:
            return centro
        return CentroCosteGestion.objects.filter(team=team, tipo=ambito, activo=True).order_by("codigo").first()

    proveedor = getattr(instance, "proveedor", None)

    obra = getattr(instance, "obra_planificacion", None)

    if not obra and proveedor:
        obra = _gestion_find_obra_by_legacy_v2(team, getattr(proveedor, "cod_obra_legacy", None))

    if not obra:
        obra = _gestion_find_obra_by_legacy_v2(team, getattr(instance, "cod_obra_legacy", None))

    if obra:
        instance.obra_planificacion = obra
        if not getattr(instance, "cod_obra_legacy", None) and getattr(obra, "legacy_cod_obra", None):
            instance.cod_obra_legacy = str(obra.legacy_cod_obra)

        centro = CentroCosteGestion.objects.filter(
            team=team,
            tipo="OBRA",
            obra_planificacion=obra,
            activo=True,
        ).first()
        if centro:
            return centro

    return CentroCosteGestion.objects.filter(team=team, codigo="OBRA_SIN_ASIGNAR", activo=True).first()


def _gestion_set_ambito_centro_auto_v2(instance):
    centro = _gestion_resolve_centro_coste_auto_v2(instance)
    if centro:
        instance.centro_coste = centro


try:
    from django.db.models.signals import pre_save
    from django.dispatch import receiver
    from apps.gestion.models import AlbaranProveedorGestion, FacturaProveedorGestion

    @receiver(pre_save, sender=AlbaranProveedorGestion, dispatch_uid="gestion_albaran_ambito_centro_auto_v2")
    def _gestion_albaran_ambito_centro_auto_v2(sender, instance, **kwargs):
        _gestion_set_ambito_centro_auto_v2(instance)

    @receiver(pre_save, sender=FacturaProveedorGestion, dispatch_uid="gestion_factura_ambito_centro_auto_v2")
    def _gestion_factura_ambito_centro_auto_v2(sender, instance, **kwargs):
        _gestion_set_ambito_centro_auto_v2(instance)

except Exception:
    pass
