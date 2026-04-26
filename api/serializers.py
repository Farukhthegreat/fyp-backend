from rest_framework import serializers
from django.contrib.auth.models import User
from .name_utils import normalize_name_parts
from .models import (
    Farm, DiagnosisResult, Supplier, SupplierProduct,
    Expert, ChatRoom, ChatMessage, DailyTask, TaskCompletion, Article,
    VaccinationRecord, MortalityLog, TreatmentRecord,
)


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
    flock_size = serializers.IntegerField(required=False)
    fcm_token = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        pass

    def to_representation(self, instance):
        data = super().to_representation(instance)
        first_name, last_name = normalize_name_parts(
            data.get('first_name', ''),
            data.get('last_name', ''),
        )
        data['first_name'] = first_name
        data['last_name'] = last_name
        return data

    def update(self, instance, validated_data):
        user_data = validated_data.get('user', {})
        user = instance.user
        clean_first_name, clean_last_name = normalize_name_parts(
            user_data.get('first_name', user.first_name),
            user_data.get('last_name', user.last_name),
        )
        if 'email' in user_data:
            user.email = user_data['email']
        if 'first_name' in user_data:
            user.first_name = clean_first_name
        if 'last_name' in user_data:
            user.last_name = clean_last_name
        user.save()

        if 'name' in validated_data:
            instance.name = validated_data['name']
        if 'location' in validated_data:
            instance.location = validated_data['location']
        if 'flock_size' in validated_data:
            instance.flock_size = validated_data['flock_size']
        if 'fcm_token' in validated_data:
            instance.fcm_token = validated_data['fcm_token']
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
            'all_probabilities',
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


class DiagnosisResultDetailSerializer(DiagnosisResultSerializer):
    class Meta(DiagnosisResultSerializer.Meta):
        fields = DiagnosisResultSerializer.Meta.fields + ['analysis_payload']

    def to_representation(self, obj):
        data = super().to_representation(obj)
        payload = data.pop('analysis_payload', None) or {}
        if isinstance(payload, dict):
            for key in (
                'image_stage_probabilities',
                'image_stage_top_class',
                'image_stage_top_confidence',
                'yolo_detected',
                'yolo_confidence',
                'crop_preview_data_url',
                'xai',
                'pipeline',
                'accepted',
                'rejected',
                'weather',
                'tips',
            ):
                if key in payload:
                    data[key] = payload[key]
        return data


class SupplierProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierProduct
        fields = ['id', 'name', 'name_ur', 'price', 'unit', 'is_available']


class SupplierSerializer(serializers.ModelSerializer):
    products = SupplierProductSerializer(many=True, read_only=True)

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'supplier_type', 'phone', 'whatsapp',
            'location', 'latitude', 'longitude', 'is_active', 'products',
        ]


class SupplierListSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source='products.count', read_only=True)

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'supplier_type', 'phone', 'whatsapp',
            'location', 'is_active', 'product_count',
        ]


class ExpertListSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.CharField(source='user.email', read_only=True)

    def get_name(self, obj):
        full = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full or obj.user.username

    class Meta:
        model = Expert
        fields = [
            'id', 'name', 'email', 'specialization', 'specialization_urdu',
            'city', 'city_urdu',
            'years_experience', 'rating',
        ]


class ExpertDetailSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.CharField(source='user.email', read_only=True)

    def get_name(self, obj):
        full = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full or obj.user.username

    class Meta:
        model = Expert
        fields = [
            'id', 'name', 'email',
            'specialization', 'specialization_urdu',
            'phone', 'whatsapp', 'is_available',
            'qualification', 'qualification_urdu',
            'clinic_name', 'clinic_name_urdu',
            'city', 'city_urdu',
            'years_experience',
            'consultation_hours', 'consultation_hours_urdu',
            'consultation_fee', 'languages',
            'about', 'about_urdu',
            'rating', 'total_consultations',
        ]


class ChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.first_name', read_only=True)

    class Meta:
        model = ChatMessage
        fields = ['id', 'sender', 'sender_name', 'message', 'is_read', 'created_at']
        read_only_fields = ['sender', 'created_at']


class ChatRoomSerializer(serializers.ModelSerializer):
    expert_name = serializers.CharField(source='expert.first_name', read_only=True)
    farmer_name = serializers.CharField(source='farmer.first_name', read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            'id', 'farmer', 'expert', 'farmer_name', 'expert_name',
            'last_message', 'created_at', 'updated_at',
        ]
        read_only_fields = ['farmer', 'created_at', 'updated_at']

    def get_last_message(self, obj):
        msg = obj.messages.order_by('-created_at').first()
        if msg:
            return {'message': msg.message, 'created_at': msg.created_at, 'sender_name': msg.sender.first_name}
        return None


class DailyTaskSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()

    class Meta:
        model = DailyTask
        fields = [
            'id', 'name', 'name_ur', 'description', 'description_ur',
            'category', 'time_of_day', 'is_completed',
        ]

    def get_is_completed(self, obj):
        request = self.context.get('request')
        date = self.context.get('date')
        if request and date:
            return TaskCompletion.objects.filter(
                user=request.user, task=obj, date=date
            ).exists()
        return False


class ArticleListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['id', 'title', 'title_ur', 'category', 'image_url',
                  'is_auto_generated', 'created_at']


class ArticleDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = [
            'id', 'title', 'title_ur', 'content', 'content_ur',
            'category', 'image_url', 'is_auto_generated', 'created_at',
        ]


class VaccinationRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = VaccinationRecord
        fields = [
            'id', 'vaccine_name', 'vaccine_name_ur', 'date_administered',
            'next_due_date', 'flock_age_days', 'dose_count', 'notes', 'created_at',
        ]
        read_only_fields = ['created_at']


class MortalityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MortalityLog
        fields = ['id', 'date', 'count', 'cause', 'notes', 'created_at']
        read_only_fields = ['created_at']


class TreatmentRecordSerializer(serializers.ModelSerializer):
    diagnosis_disease = serializers.CharField(
        source='diagnosis_result.disease_name', read_only=True, default=None
    )

    class Meta:
        model = TreatmentRecord
        fields = [
            'id', 'diagnosis_result', 'diagnosis_disease', 'medication_name',
            'start_date', 'end_date', 'dosage', 'notes', 'created_at',
        ]
        read_only_fields = ['created_at']
