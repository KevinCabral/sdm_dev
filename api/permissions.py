"""
Custom DRF permission classes and helpers for Mesa-based access control.

Roles:
- Superuser / `admin` group  → full access to everything
- `delegado` group           → read-only access to ONLY the mesas assigned via UserMesa,
                               and the eleitores belonging to those mesas
- Authenticated default      → no access to eleitores/mesas unless in one of the above
"""
from rest_framework import permissions

from apps.mesa.models import UserMesa


# ---------- Helpers ----------

def is_admin(user) -> bool:
    """User is superuser or in the 'admin' group."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__iexact="admin").exists()


def is_delegado(user) -> bool:
    """User belongs to the 'delegado' group."""
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name__iexact="delegado").exists()


def user_mesa_ids(user):
    """Return the list of Mesa.id this user is assigned to via UserMesa."""
    if not user or not user.is_authenticated:
        return []
    return list(
        UserMesa.objects.filter(user=user, mesa__isnull=False)
        .values_list("mesa_id", flat=True)
        .distinct()
    )


def user_mesa_numbers(user):
    """Return the list of Mesa.nr_mesa strings this user is assigned to."""
    if not user or not user.is_authenticated:
        return []
    return list(
        UserMesa.objects.filter(user=user, mesa__isnull=False)
        .values_list("mesa__nr_mesa", flat=True)
        .distinct()
    )


# ---------- Permission classes ----------

class IsAdmin(permissions.BasePermission):
    """Allow only superusers / 'admin' group."""

    message = "Apenas administradores têm acesso a este recurso."

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrDelegado(permissions.BasePermission):
    """
    Authenticated AND (admin OR delegado).

    Object-level rules (enforced by viewsets via queryset filtering, but
    re-checked here for safety):
      - Admin: any object
      - Delegado: object must belong to one of their assigned mesas
        (the viewset must implement `_object_belongs_to_user(obj, user)`).
    """

    message = "Sem permissão para aceder a este recurso."

    def has_permission(self, request, view):
        return is_admin(request.user) or is_delegado(request.user)

    def has_object_permission(self, request, view, obj):
        if is_admin(request.user):
            return True
        check = getattr(view, "_object_belongs_to_user", None)
        if callable(check):
            return check(obj, request.user)
        return True


class IsAdminOrReadOnlyDelegado(IsAdminOrDelegado):
    """Same as above, but delegados only get safe (read) methods."""

    def has_permission(self, request, view):
        if is_admin(request.user):
            return True
        if is_delegado(request.user):
            return request.method in permissions.SAFE_METHODS
        return False
