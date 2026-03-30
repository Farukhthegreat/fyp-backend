from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Farm, DiagnosisResult


class FarmSerializer(serializers.ModelSerializer):
    """
    Serializer for Farm model.
    """
    class Meta:
        model = Farm
        fields = ['id', 'name', 'location', 'flock_size']


class UserProfileSerializer(serializers.Serializer):
    """
    Serializer for user profile combining User and Farm data.
    """
    id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    farm_name = serializers.CharField(source='name')
    location = serializers.CharField()

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        # Update User fields
        user = instance.user
        user.email = validated_data.get('email', user.email)
        user.first_name = validated_data.get('first_name', user.first_name)
        user.last_name = validated_data.get('last_name', user.last_name)
        user.save()

        # Update Farm fields
        instance.name = validated_data.get('farm_name', instance.name)
        instance.location = validated_data.get('location', instance.location)
        instance.save()

        return instance


class DiagnosisResultSerializer(serializers.ModelSerializer):
    """
    Serializer for DiagnosisResult model.
    disease_name and confidence are read-only as they come from the AI model.
    image_url returns the full URL for the uploaded image.
    """
    image_url = serializers.SerializerMethodField()
    farm_name = serializers.SerializerMethodField()

    class Meta:
        model = DiagnosisResult
        fields = [
            'id',
            'image',
            'image_url',
            'disease_name',
            'confidence',
            'source',
            'status',
            'description',
            'notes',
            'farm_name',
            'created_at',
        ]
        read_only_fields = ['created_at']
        extra_kwargs = {
            'image': {'required': False, 'allow_null': True},
        }

    def get_image_url(self, obj):
        """Return the full URL for the image."""
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_farm_name(self, obj):
        """Return the farm name from the related farm or user's first farm."""
        if obj.farm and obj.farm.name:
            return obj.farm.name
        # Fallback: get user's first farm
        from .models import Farm
        farm = Farm.objects.filter(user=obj.user).first()
        return farm.name if farm else 'My Farm'
