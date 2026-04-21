from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from apps.militantes.models import Militantes
from django.db import transaction
from django.utils.text import slugify

class Command(BaseCommand):
    help = 'Creates user accounts for entries in the militantes table'

    def handle(self, *args, **options):
        with transaction.atomic():
            for militante in Militantes.objects.all():
                username = militante.email_pessoal.strip() if militante.email_pessoal else self.generate_username(militante.nome_completo)
                
                if not username:
                    self.stdout.write(self.style.ERROR(f'Skipping militante ID {militante.id} due to missing username.'))
                    continue

                if not User.objects.filter(username=username).exists():
                    try:
                        user = User.objects.create_user(
                            username=username,
                            email=militante.email_pessoal,
                            password='defaultpassword'  # Consider a more secure handling
                        )
                        self.stdout.write(self.style.SUCCESS(f'Successfully created user for {username}'))
                    except Exception as e:
                        raise CommandError(f'Error creating user for {username}: {str(e)}')
                else:
                    self.stdout.write(self.style.WARNING(f'User already exists for {username}'))

    def generate_username(self, nome_completo):
        parts = nome_completo.split()
        if len(parts) > 1:
            return f"{slugify(parts[0])}.{slugify(parts[-1])}".lower()
        elif parts:
            return slugify(parts[0]).lower()
        return ''
