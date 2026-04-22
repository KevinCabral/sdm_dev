"""
ViewSets for Mesa, UserMesa and Eleitores resources with role-based access:

- Admin (superuser or 'admin' group)  → unrestricted
- Delegado ('delegado' group)         → only their assigned mesas + matching eleitores
- Anyone else                         → 403

Filtering on Eleitores is performed by `nr_mesa` string match against the
`Mesa.nr_mesa` of the user's UserMesa entries (Eleitor.nr_mesa is a CharField,
not a FK to Mesa).
"""
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.eleitores.models import Eleitores
from apps.mesa.models import Mesa, UserMesa

from .permissions import (
    IsAdmin,
    IsAdminOrDelegado,
    IsAdminOrReadOnlyDelegado,
    is_admin,
    is_delegado,
    user_mesa_ids,
    user_mesa_numbers,
)
from .serializers_mesa import (
    EleitorListSerializer,
    EleitorMarkSerializer,
    EleitorSerializer,
    MesaSerializer,
    UserMesaBulkAssignSerializer,
    UserMesaSerializer,
    UserMiniSerializer,
)


# ---------- Mesas ----------

class MesaViewSet(viewsets.ModelViewSet):
    """
    /api/mesas/

    - GET (list/detail): admin sees all, delegado sees only assigned mesas.
    - POST/PUT/PATCH/DELETE: admin only.
    """

    serializer_class = MesaSerializer
    permission_classes = [IsAdminOrReadOnlyDelegado]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nr_mesa"]
    ordering_fields = ["nr_mesa", "createdAt", "updatedAt"]
    ordering = ["nr_mesa"]

    def get_queryset(self):
        qs = Mesa.objects.all()
        user = self.request.user
        if is_admin(user):
            return qs
        if is_delegado(user):
            return qs.filter(id__in=user_mesa_ids(user))
        return qs.none()

    def _object_belongs_to_user(self, obj, user):
        return obj.id in user_mesa_ids(user)

    @action(detail=True, methods=["get"], url_path="eleitores")
    def eleitores(self, request, pk=None):
        """List eleitores belonging to this mesa (respects user permissions)."""
        mesa = self.get_object()
        qs = Eleitores.objects.filter(nr_mesa=mesa.nr_mesa, falecido=False)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EleitorListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(EleitorListSerializer(qs, many=True).data)


# ---------- UserMesa (admin-only assignments) ----------

class UserMesaViewSet(viewsets.ModelViewSet):
    """
    /api/user-mesas/  (admin only)

    Manage the UserMesa pivot — assign delegados to mesas.
    """

    serializer_class = UserMesaSerializer
    permission_classes = [IsAdmin]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-createdAt"]

    def get_queryset(self):
        qs = UserMesa.objects.select_related("user", "mesa").all()
        user_id = self.request.query_params.get("user")
        mesa_id = self.request.query_params.get("mesa")
        if user_id:
            qs = qs.filter(user_id=user_id)
        if mesa_id:
            qs = qs.filter(mesa_id=mesa_id)
        return qs

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        """
        Replace a user's mesa assignments with the provided list.

        Body: {"user": <user_id>, "mesas": [<mesa_id>, ...]}
        """
        serializer = UserMesaBulkAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        mesas = serializer.validated_data["mesas"]

        UserMesa.objects.filter(user=user).delete()
        UserMesa.objects.bulk_create(
            [UserMesa(user=user, mesa=mesa) for mesa in mesas]
        )
        created = UserMesa.objects.filter(user=user).select_related("user", "mesa")
        return Response(
            UserMesaSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path=r"by-user/(?P<user_id>\d+)")
    def by_user(self, request, user_id=None):
        """List the mesas assigned to a given user."""
        qs = self.get_queryset().filter(user_id=user_id)
        return Response(self.get_serializer(qs, many=True).data)


# ---------- Eleitores ----------

class EleitorViewSet(viewsets.ModelViewSet):
    """
    /api/eleitores/

    - List/Detail: admin → all; delegado → only eleitores in their mesas.
    - Create/Update/Delete: admin only (delegado is read-only on collection).
    - Custom action `mark-descarga` (PATCH): allowed for delegado on owned eleitores
      so the field operator can flag who already voted.
    """

    permission_classes = [IsAdminOrDelegado]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "nominho", "filiacao"]
    ordering_fields = ["nome", "nr_eleitor", "datahora_atualizacao"]
    ordering = ["nome"]

    def get_serializer_class(self):
        if self.action == "list":
            return EleitorListSerializer
        if self.action == "mark_descarga":
            return EleitorMarkSerializer
        return EleitorSerializer

    def get_queryset(self):
        qs = Eleitores.objects.filter(falecido=False)
        user = self.request.user

        if is_admin(user):
            pass
        elif is_delegado(user):
            mesas = user_mesa_numbers(user)
            if not mesas:
                return qs.none()
            qs = qs.filter(nr_mesa__in=mesas)
        else:
            return qs.none()

        # Manual GET filters (no django-filter dependency)
        params = self.request.query_params
        for field in ("nr_mesa", "nr_eleitor", "concelho", "zona"):
            value = params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        for boolean_field in ("mpd", "indeciso", "ausente", "nao_vai_votar", "descarga"):
            value = params.get(boolean_field)
            if value is not None and value != "":
                qs = qs.filter(**{boolean_field: value.lower() in ("1", "true", "yes")})
        return qs

    def _object_belongs_to_user(self, obj, user):
        return obj.nr_mesa in user_mesa_numbers(user)

    # Restrict write methods for delegados on the collection level
    def _check_write_allowed(self):
        if is_admin(self.request.user):
            return
        raise PermissionDenied("Apenas administradores podem modificar eleitores.")

    def create(self, request, *args, **kwargs):
        self._check_write_allowed()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._check_write_allowed()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._check_write_allowed()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Soft-delete: set falecido=True instead of removing the row."""
        self._check_write_allowed()
        instance = self.get_object()
        instance.falecido = True
        instance.save(update_fields=["falecido", "datahora_atualizacao"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"], url_path="mark-descarga")
    def mark_descarga(self, request, pk=None):
        """
        Mark/unmark an eleitor as voted (descarga).

        Allowed for admins, and for delegados on eleitores that belong to
        one of their assigned mesas (object-level check via permission class).
        """
        eleitor = self.get_object()  # triggers has_object_permission
        serializer = EleitorMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        eleitor.descarga = serializer.validated_data["descarga"]
        eleitor.save(update_fields=["descarga", "datahora_atualizacao"])
        return Response(EleitorSerializer(eleitor).data)

    @action(detail=False, methods=["get"], url_path=r"by-nr-eleitor/(?P<nr_eleitor>\d+)")
    def by_nr_eleitor(self, request, nr_eleitor=None):
        """
        Lookup a single eleitor by `nr_eleitor`.

        Respects the same access scope as the list endpoint:
        - admin: any eleitor
        - delegado: only if the eleitor's mesa is among their assignments
        Returns 404 if not found OR not visible to the requesting user.
        """
        eleitor = self.get_queryset().filter(nr_eleitor=nr_eleitor).first()
        if eleitor is None:
            return Response(
                {"detail": "Eleitor não encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(EleitorSerializer(eleitor).data)

    @action(detail=False, methods=["get"], url_path="my-mesas")
    def my_mesas(self, request):
        """Convenience endpoint: mesas the requesting user has access to."""
        user = request.user
        if is_admin(user):
            mesas = Mesa.objects.all()
        else:
            mesas = Mesa.objects.filter(id__in=user_mesa_ids(user))
        return Response(MesaSerializer(mesas.order_by("nr_mesa"), many=True).data)
