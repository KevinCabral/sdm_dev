from rest_framework import serializers
from django.contrib.auth.models import Group, User


# from users.models import Profile

try:

    from home.models import Product

except:
    pass 

class ProductSerializer(serializers.ModelSerializer):
    class Meta:

        try:
            model = Product
        except:
            pass    
        fields = '__all__'


# class ProfileSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Profile
#         fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'password', 'email')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)




# class GroupSerializer(serializers.HyperlinkedModelSerializer):
#     class Meta:
#         model = Group
#         fields = ['url', 'name']
