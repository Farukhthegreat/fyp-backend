from django.db import models
from django.contrib.auth.models import User


class Farm(models.Model):
    """
    Farm model representing a farm owned by a user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='farms')
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    flock_size = models.IntegerField()
    fcm_token = models.CharField(max_length=512, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.user.username}"

    class Meta:
        ordering = ['-created_at']


class DiagnosisResult(models.Model):
    """
    DiagnosisResult model representing a disease diagnosis result from an image.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='diagnoses')
    farm = models.ForeignKey(Farm, on_delete=models.SET_NULL, null=True, blank=True, related_name='diagnoses')
    image = models.ImageField(upload_to='diagnosis_images/', null=True, blank=True)
    disease_name = models.CharField(max_length=255)
    confidence = models.FloatField()
    source = models.CharField(max_length=20, default='ai')
    status = models.CharField(max_length=20, default='Alert')
    description = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    all_probabilities = models.JSONField(null=True, blank=True)
    analysis_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.disease_name} - {self.confidence:.2f}% - {self.user.username}"

    class Meta:
        ordering = ['-created_at']


class Supplier(models.Model):
    SUPPLIER_TYPES = [('feed', 'Feed'), ('vaccine', 'Vaccine'), ('equipment', 'Equipment')]
    name = models.CharField(max_length=255)
    supplier_type = models.CharField(max_length=20, choices=SUPPLIER_TYPES)
    phone = models.CharField(max_length=20)
    whatsapp = models.CharField(max_length=20)
    location = models.CharField(max_length=255)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.supplier_type})"

    class Meta:
        ordering = ['name']


class SupplierProduct(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    name_ur = models.CharField(max_length=255, blank=True, default='')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=50, default='per bag')
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - PKR {self.price}"

    class Meta:
        ordering = ['name']


class Expert(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='expert_profile')
    specialization = models.CharField(max_length=255)
    specialization_urdu = models.CharField(max_length=255, blank=True, default='')
    qualification = models.CharField(max_length=255, blank=True, default='')
    qualification_urdu = models.CharField(max_length=255, blank=True, default='')
    clinic_name = models.CharField(max_length=255, blank=True, default='')
    clinic_name_urdu = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=120, blank=True, default='')
    city_urdu = models.CharField(max_length=120, blank=True, default='')
    years_experience = models.PositiveIntegerField(default=0)
    consultation_hours = models.CharField(max_length=255, blank=True, default='')
    consultation_hours_urdu = models.CharField(max_length=255, blank=True, default='')
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    languages = models.CharField(max_length=255, blank=True, default='')
    about = models.TextField(blank=True, default='')
    about_urdu = models.TextField(blank=True, default='')
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=4.50)
    total_consultations = models.PositiveIntegerField(default=0)
    phone = models.CharField(max_length=20, blank=True, default='')
    whatsapp = models.CharField(max_length=20, blank=True, default='')
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.first_name} - {self.specialization}"

    class Meta:
        ordering = ['specialization']


class ChatRoom(models.Model):
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='farmer_chat_rooms')
    expert = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expert_chat_rooms')
    firestore_room_id = models.CharField(max_length=255, blank=True, default='', help_text='Firestore document ID for this room')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Chat: {self.farmer.username} <> {self.expert.username}"

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['farmer', 'expert']


class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender.username}: {self.message[:50]}"

    class Meta:
        ordering = ['created_at']


class DailyTask(models.Model):
    TASK_CATEGORIES = [
        ('water', 'Water'), ('feed', 'Feed'), ('egg', 'Egg Collection'),
        ('light', 'Lighting'), ('temperature', 'Temperature'),
        ('health', 'Health Check'), ('cleaning', 'Cleaning'),
    ]
    name = models.CharField(max_length=255)
    name_ur = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    description_ur = models.TextField(blank=True, default='')
    category = models.CharField(max_length=20, choices=TASK_CATEGORIES)
    min_flock_size = models.IntegerField(default=0)
    season = models.CharField(max_length=20, default='all')
    time_of_day = models.CharField(max_length=20, default='morning')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.time_of_day})"

    class Meta:
        ordering = ['time_of_day', 'name']


class TaskCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_completions')
    task = models.ForeignKey(DailyTask, on_delete=models.CASCADE, related_name='completions')
    completed_at = models.DateTimeField(auto_now_add=True)
    date = models.DateField()

    class Meta:
        ordering = ['-completed_at']
        unique_together = ['user', 'task', 'date']


class Article(models.Model):
    ARTICLE_CATEGORIES = [
        ('health', 'Health'), ('disease', 'Disease Prevention'),
        ('seasonal', 'Seasonal Care'), ('nutrition', 'Nutrition'),
        ('management', 'Farm Management'),
    ]
    title = models.CharField(max_length=255)
    title_ur = models.CharField(max_length=255, blank=True, default='')
    content = models.TextField()
    content_ur = models.TextField(blank=True, default='')
    category = models.CharField(max_length=20, choices=ARTICLE_CATEGORIES)
    image_url = models.URLField(blank=True, default='')
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']


class VaccinationRecord(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='vaccinations')
    vaccine_name = models.CharField(max_length=255)
    vaccine_name_ur = models.CharField(max_length=255, blank=True, default='')
    date_administered = models.DateField()
    next_due_date = models.DateField(null=True, blank=True)
    flock_age_days = models.IntegerField(default=0)
    dose_count = models.IntegerField(default=1)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.vaccine_name} - {self.farm.name} ({self.date_administered})"

    class Meta:
        ordering = ['-date_administered']


class MortalityLog(models.Model):
    CAUSE_CHOICES = [
        ('disease', 'Disease'), ('unknown', 'Unknown'),
        ('accident', 'Accident'), ('heat', 'Heat Stress'), ('cold', 'Cold Stress'),
    ]
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='mortality_logs')
    date = models.DateField()
    count = models.IntegerField(default=1)
    cause = models.CharField(max_length=20, choices=CAUSE_CHOICES, default='unknown')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.count} birds - {self.cause} - {self.date}"

    class Meta:
        ordering = ['-date']


class TreatmentRecord(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='treatments')
    diagnosis_result = models.ForeignKey(
        DiagnosisResult, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatments'
    )
    medication_name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    dosage = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.medication_name} - {self.farm.name} ({self.start_date})"

    class Meta:
        ordering = ['-start_date']


class MarketRateOverride(models.Model):
    """
    Admin-entered daily poultry rates. Takes priority over scraped AGBRO data.
    One row per (region_key, date). Set `active=False` to disable without delete.

    Peti logic: 1 tray = 30 eggs, 1 peti = 12 trays = 360 eggs.
    egg_peti_price is computed as egg_tray_price * 12 when writing to Firestore.
    """
    REGION_CHOICES = [
        ('punjab', 'Punjab (Market Committee official rate)'),
    ]

    region_key = models.CharField(
        max_length=32, choices=REGION_CHOICES, default='punjab', db_index=True,
    )
    date = models.CharField(max_length=10, db_index=True, help_text='YYYY-MM-DD')
    egg_tray_price = models.PositiveIntegerField(help_text='PKR per 30 eggs')
    broiler_live_per_kg = models.PositiveIntegerField(help_text='PKR per kg live')
    feed_starter_per_bag = models.PositiveIntegerField(null=True, blank=True, help_text='PKR per 50 kg bag')
    feed_grower_per_bag = models.PositiveIntegerField(null=True, blank=True)
    feed_finisher_per_bag = models.PositiveIntegerField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default='')
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'region_key']
        unique_together = [('region_key', 'date')]

    def __str__(self):
        return f"{self.region_key} {self.date} — tray PKR {self.egg_tray_price}"

    @property
    def egg_peti_price(self) -> int:
        return int(self.egg_tray_price) * 12
