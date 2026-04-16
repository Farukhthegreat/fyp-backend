from django.contrib import admin
from django.contrib import messages
from .models import (
    Farm, DiagnosisResult, Supplier, SupplierProduct,
    Expert, ChatRoom, ChatMessage, DailyTask, TaskCompletion, Article,
    MarketRateOverride,
)


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'flock_size', 'user', 'created_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'location', 'user__username', 'user__email']
    date_hierarchy = 'created_at'


@admin.register(DiagnosisResult)
class DiagnosisResultAdmin(admin.ModelAdmin):
    list_display = ['disease_name', 'confidence', 'user', 'farm', 'created_at']
    list_filter = ['disease_name', 'created_at', 'user']
    search_fields = ['disease_name', 'user__username', 'user__email']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at']


class SupplierProductInline(admin.TabularInline):
    model = SupplierProduct
    extra = 1


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'supplier_type', 'location', 'phone', 'is_active']
    list_filter = ['supplier_type', 'is_active']
    search_fields = ['name', 'location']
    inlines = [SupplierProductInline]


@admin.register(Expert)
class ExpertAdmin(admin.ModelAdmin):
    list_display = ['user', 'specialization', 'whatsapp', 'is_available']
    list_filter = ['specialization', 'is_available']


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ['farmer', 'expert', 'created_at', 'updated_at']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['room', 'sender', 'message', 'is_read', 'created_at']
    list_filter = ['is_read']


@admin.register(DailyTask)
class DailyTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'time_of_day', 'season', 'is_active']
    list_filter = ['category', 'time_of_day', 'season', 'is_active']


@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    list_display = ['user', 'task', 'date', 'completed_at']
    list_filter = ['date']


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'is_published', 'created_at']
    list_filter = ['category', 'is_published']
    search_fields = ['title', 'content']


@admin.register(MarketRateOverride)
class MarketRateOverrideAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'region_key', 'egg_tray_price', 'egg_peti_display',
        'broiler_live_per_kg', 'doc_price', 'active', 'updated_at',
    ]
    list_filter = ['region_key', 'active', 'date']
    search_fields = ['region_key', 'date', 'note']
    ordering = ['-date', 'region_key']
    readonly_fields = ['created_at', 'updated_at', 'egg_peti_display']
    actions = ['push_to_firestore']

    fieldsets = (
        ('Region & Date', {
            'fields': ('region_key', 'date', 'active', 'note'),
        }),
        ('Egg Prices', {
            'fields': ('egg_tray_price', 'egg_peti_display'),
            'description': '1 tray = 30 eggs · 1 peti = 12 trays = 360 eggs. '
                           'Peti price is computed as tray × 12 automatically.',
        }),
        ('Broiler & DOC', {
            'fields': ('broiler_live_per_kg', 'doc_price'),
        }),
        ('Feed (50 kg bag, optional)', {
            'fields': ('feed_starter_per_bag', 'feed_grower_per_bag', 'feed_finisher_per_bag'),
            'classes': ('collapse',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def egg_peti_display(self, obj):
        return f'PKR {obj.egg_peti_price:,}' if obj.pk else '—'
    egg_peti_display.short_description = 'Peti price (auto)'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Push the override straight to Firestore so the app updates immediately,
        # bypassing the cron loop. FCM fan-out fires via the Cloud Function.
        pushed = _sync_override_to_firestore(obj)
        if pushed:
            messages.success(request, f'Pushed {obj.region_key} {obj.date} to Firestore.')
        else:
            messages.warning(request, f'Saved locally. Firestore push failed or disabled — run fetch_market_rates to sync.')

    @admin.action(description='Push selected rates to Firestore now')
    def push_to_firestore(self, request, queryset):
        ok, fail = 0, 0
        for obj in queryset:
            if _sync_override_to_firestore(obj):
                ok += 1
            else:
                fail += 1
        self.message_user(request, f'Pushed {ok} · failed {fail}', level=messages.INFO)


def _sync_override_to_firestore(obj: 'MarketRateOverride') -> bool:
    """Mirror one admin override into Firestore. Returns True on success."""
    try:
        from django.conf import settings
        from firebase_admin import firestore as admin_firestore
        if not getattr(settings, 'FIREBASE_INITIALIZED', False):
            return False
        from api.management.commands.fetch_market_rates import (
            REGION, TRAYS_PER_PETI, EGGS_PER_PETI, EGGS_PER_TRAY,
        )
        if obj.region_key != REGION['key']:
            return False
        tray = int(obj.egg_tray_price)
        live = int(obj.broiler_live_per_kg)
        payload = {
            'date': obj.date,
            'region': REGION['name'],
            'region_key': REGION['key'],
            'province': REGION['province'],
            'egg_tray_price': tray,
            'egg_peti_price': tray * TRAYS_PER_PETI,
            'egg_dozen_price': int(tray / 2.5),
            'broiler_live_per_kg': live,
            'broiler_live_wholesale': int(live * 0.96),
            'broiler_farm_gate': int(live * 0.92),
            'broiler_meat_per_kg': int(live * 1.50),
            'doc_price': int(obj.doc_price or 110),
            'feed_starter_per_bag': int(obj.feed_starter_per_bag or 9800),
            'feed_grower_per_bag': int(obj.feed_grower_per_bag or 9500),
            'feed_finisher_per_bag': int(obj.feed_finisher_per_bag or 9200),
            'source': 'admin',
            'source_date': obj.date,
            'image_url': '',
            'scraped': True,
            'eggs_per_peti': EGGS_PER_PETI,
            'trays_per_peti': TRAYS_PER_PETI,
            'eggs_per_tray': EGGS_PER_TRAY,
            'updated_at': admin_firestore.SERVER_TIMESTAMP,
        }
        db = admin_firestore.client()
        doc_id = f'{obj.date}_{obj.region_key}'
        db.collection('market_rates').document(doc_id).set(payload, merge=True)
        db.collection('market_rates_latest').document(obj.region_key).set(payload, merge=True)
        return True
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger(__name__).warning('Firestore sync failed: %s', e)
        return False

