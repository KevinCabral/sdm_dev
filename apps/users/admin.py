from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User
from django.contrib.admin.sites import AlreadyRegistered, NotRegistered


class TeamStatusFilter(admin.SimpleListFilter):
	title = "Estado de equipa"
	parameter_name = "is_staff"

	def lookups(self, request, model_admin):
		return (
			("1", "Sim"),
			("0", "Nao"),
		)

	def queryset(self, request, queryset):
		value = self.value()
		if value == "1":
			return queryset.filter(is_staff=True)
		if value == "0":
			return queryset.filter(is_staff=False)
		return queryset


class SuperuserStatusFilter(admin.SimpleListFilter):
	title = "Superutilizador"
	parameter_name = "is_superuser"

	def lookups(self, request, model_admin):
		return (
			("1", "Sim"),
			("0", "Nao"),
		)

	def queryset(self, request, queryset):
		value = self.value()
		if value == "1":
			return queryset.filter(is_superuser=True)
		if value == "0":
			return queryset.filter(is_superuser=False)
		return queryset


class ActiveStatusFilter(admin.SimpleListFilter):
	title = "Estado da conta"
	parameter_name = "is_active"

	def lookups(self, request, model_admin):
		return (
			("1", "Ativo"),
			("0", "Inativo"),
		)

	def queryset(self, request, queryset):
		value = self.value()
		if value == "1":
			return queryset.filter(is_active=True)
		if value == "0":
			return queryset.filter(is_active=False)
		return queryset


class UserAdmin(DjangoUserAdmin):
	list_per_page = 10
	list_filter = (TeamStatusFilter, SuperuserStatusFilter, ActiveStatusFilter, "groups")
	change_list_template = "admin/auth/user/change_list.html"


class GroupAdmin(DjangoGroupAdmin):
	list_per_page = 10
	change_list_template = "admin/auth/group/change_list.html"


for model in (User, Group):
	try:
		admin.site.unregister(model)
	except NotRegistered:
		pass


try:
	admin.site.register(User, UserAdmin)
except AlreadyRegistered:
	pass


try:
	admin.site.register(Group, GroupAdmin)
except AlreadyRegistered:
	pass
