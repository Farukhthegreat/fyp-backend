import math
from datetime import date, timedelta
from collections import defaultdict

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status, generics
from django.db.models import Sum
from .models import (
    DiagnosisResult, Farm, Supplier, Expert, ChatRoom, ChatMessage,
    DailyTask, TaskCompletion, Article,
    VaccinationRecord, MortalityLog, TreatmentRecord,
)
from .serializers import (
    DiagnosisResultSerializer, UserProfileSerializer,
    SupplierSerializer, SupplierListSerializer, ExpertSerializer,
    ChatRoomSerializer, ChatMessageSerializer,
    DailyTaskSerializer, ArticleListSerializer, ArticleDetailSerializer,
    VaccinationRecordSerializer, MortalityLogSerializer, TreatmentRecordSerializer,
)
from .ai_engine import predict_disease
from .notifications import send_fcm_notification
from firebase_admin import firestore as admin_firestore


class HealthView(APIView):
    """
    Public health check endpoint - no authentication required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'status': 'ok'})


class ProtectedView(APIView):
    """
    Protected endpoint - requires Firebase authentication.
    The user must include a valid Firebase ID token in the Authorization header.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'message': 'You are authenticated!',
            'user_id': request.user.id,
            'username': request.user.username,  # This is the Firebase UID
            'email': request.user.email,
            'display_name': request.user.first_name,
        })


class ProfileView(APIView):
    """
    GET /api/profile/: Returns user profile with farm details.
    PUT /api/profile/: Updates user and farm profile data in PostgreSQL.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Get the user's first farm (or primary farm)
            farm = Farm.objects.filter(user=request.user).first()
            
            if not farm:
                return Response(
                    {'error': 'No farm assigned to this user'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = UserProfileSerializer(farm)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request):
        try:
            # Get the user's first farm (or primary farm)
            farm = Farm.objects.filter(user=request.user).first()
            
            if not farm:
                return Response(
                    {'error': 'No farm assigned to this user'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = UserProfileSerializer(farm, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PublicDataView(APIView):
    """
    Public endpoint that doesn't require authentication.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'message': 'This is public data accessible to everyone',
            'data': ['item1', 'item2', 'item3']
        })


class DiagnoseView(APIView):
    """
    POST endpoint to diagnose poultry disease from an uploaded image.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Check if image is provided
        if 'image' not in request.FILES:
            return Response(
                {'error': 'No image provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        image_file = request.FILES['image']

        try:
            prediction = predict_disease(image_file)
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Create DiagnosisResult in the database
        is_healthy = prediction['disease_name'].lower() == 'healthy'
        farm = Farm.objects.filter(user=request.user).first()
        diagnosis = DiagnosisResult.objects.create(
            user=request.user,
            farm=farm,
            image=image_file,
            disease_name=prediction['disease_name'],
            confidence=prediction['confidence'],
            source='ai',
            status='Healthy' if is_healthy else 'Alert',
        )

        # Serialize and return the result with request context for full image URL
        serializer = DiagnosisResultSerializer(diagnosis, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HistoryView(generics.ListCreateAPIView):
    """
    GET endpoint to retrieve all diagnosis results for the authenticated user.
    Results are sorted by newest first.
    Supports optional ?status= query param for filtering:
      - 'Healthy' → only healthy diagnoses
      - 'Alert'   → anything that is NOT healthy
      - omitted   → all diagnoses
    Requires authentication.
    """
    serializer_class = DiagnosisResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = DiagnosisResult.objects.filter(user=self.request.user).order_by('-created_at')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            if status_filter.lower() == 'alert':
                qs = qs.exclude(disease_name__iexact='healthy')
            else:
                qs = qs.filter(disease_name__iexact=status_filter)

        return qs

    def perform_create(self, serializer):
        farm = Farm.objects.filter(user=self.request.user).first()
        serializer.save(user=self.request.user, farm=farm)


class HistoryDetailView(generics.DestroyAPIView):
    """
    DELETE endpoint to remove a single diagnosis record by its ID.
    Only the record owner can delete it.
    Requires authentication.
    """
    serializer_class = DiagnosisResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DiagnosisResult.objects.filter(user=self.request.user)


class FeedCalculatorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        flock_size = request.data.get('flock_size')
        bird_age_weeks = request.data.get('bird_age_weeks', 4)
        if not flock_size or int(flock_size) <= 0:
            return Response({'error': 'Valid flock_size required'}, status=status.HTTP_400_BAD_REQUEST)

        flock_size = int(flock_size)
        bird_age_weeks = int(bird_age_weeks)

        # Feed: ~120g per bird per day for adult, scale by age
        feed_per_bird_g = min(120, 30 + bird_age_weeks * 10)
        daily_feed_kg = (flock_size * feed_per_bird_g) / 1000
        bags_per_month = math.ceil((daily_feed_kg * 30) / 50)  # 50kg bags

        # Water: ~250ml per bird per day
        daily_water_liters = (flock_size * 250) / 1000

        # Vaccination cost estimate
        vaccine_per_bird = 5  # PKR
        monthly_vaccine_cost = flock_size * vaccine_per_bird

        return Response({
            'flock_size': flock_size,
            'bird_age_weeks': bird_age_weeks,
            'daily_feed_kg': round(daily_feed_kg, 1),
            'bags_per_month': bags_per_month,
            'daily_water_liters': round(daily_water_liters, 1),
            'monthly_vaccine_cost': monthly_vaccine_cost,
            'feed_per_bird_g': feed_per_bird_g,
        })


class SupplierListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupplierListSerializer

    def get_queryset(self):
        qs = Supplier.objects.filter(is_active=True)
        supplier_type = self.request.query_params.get('type')
        if supplier_type:
            qs = qs.filter(supplier_type=supplier_type)
        return qs


class SupplierDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.filter(is_active=True)


class ExpertListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ExpertSerializer
    queryset = Expert.objects.filter(is_available=True)


class ChatRoomListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rooms = ChatRoom.objects.filter(farmer=request.user)
        serializer = ChatRoomSerializer(rooms, many=True)
        return Response(serializer.data)

    def post(self, request):
        expert_id = request.data.get('expert_id')
        if not expert_id:
            return Response({'error': 'expert_id required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            expert = Expert.objects.get(id=expert_id)
        except Expert.DoesNotExist:
            return Response({'error': 'Expert not found'}, status=status.HTTP_404_NOT_FOUND)

        room, created = ChatRoom.objects.get_or_create(
            farmer=request.user, expert=expert.user
        )
        serializer = ChatRoomSerializer(room)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ChatMessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, room_id):
        try:
            room = ChatRoom.objects.get(id=room_id, farmer=request.user)
        except ChatRoom.DoesNotExist:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

        # Mark messages from expert as read
        room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

        messages = room.messages.all()
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, room_id):
        try:
            room = ChatRoom.objects.get(id=room_id, farmer=request.user)
        except ChatRoom.DoesNotExist:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

        message_text = request.data.get('message')
        if not message_text:
            return Response({'error': 'message required'}, status=status.HTTP_400_BAD_REQUEST)

        msg = ChatMessage.objects.create(room=room, sender=request.user, message=message_text)
        room.save()  # update updated_at

        # Send FCM push notification to the recipient
        recipient = room.expert if request.user == room.farmer else room.farmer
        recipient_farm = Farm.objects.filter(user=recipient).first()
        if recipient_farm and recipient_farm.fcm_token:
            sender_name = request.user.first_name or 'Someone'
            send_fcm_notification(
                fcm_token=recipient_farm.fcm_token,
                title=f'New message from {sender_name}',
                body=message_text[:100],
                data={'type': 'chat', 'room_id': str(room.id), 'sender_name': sender_name},
            )

        # Write to Firestore for real-time Flutter stream
        try:
            db = admin_firestore.client()
            db.collection('chats').document(str(room_id)).collection('messages').document(str(msg.id)).set({
                'id': msg.id,
                'message': msg.message,
                'sender_name': request.user.first_name or request.user.username or 'User',
                'is_farmer': (request.user == room.farmer),
                'created_at': msg.created_at,
            })
        except Exception:
            pass  # Firestore write failure must not break the API

        serializer = ChatMessageSerializer(msg)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TaskListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        farm = Farm.objects.filter(user=request.user).first()
        flock_size = farm.flock_size if farm else 0

        tasks = DailyTask.objects.filter(is_active=True, min_flock_size__lte=flock_size)

        # Filter by season
        current_month = today.month
        if current_month in [6, 7, 8]:
            season = 'summer'
        elif current_month in [12, 1, 2]:
            season = 'winter'
        else:
            season = 'spring'
        tasks = tasks.filter(season__in=[season, 'all'])

        serializer = DailyTaskSerializer(tasks, many=True, context={'request': request, 'date': today})
        return Response(serializer.data)


class TaskCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        today = date.today()
        try:
            task = DailyTask.objects.get(id=task_id)
        except DailyTask.DoesNotExist:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)

        completion, created = TaskCompletion.objects.get_or_create(
            user=request.user, task=task, date=today
        )
        if not created:
            return Response({'message': 'Already completed'})
        return Response({'message': 'Task completed'}, status=status.HTTP_201_CREATED)

    def delete(self, request, task_id):
        today = date.today()
        deleted, _ = TaskCompletion.objects.filter(
            user=request.user, task_id=task_id, date=today
        ).delete()
        if deleted:
            return Response({'message': 'Task uncompleted'})
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)


class TaskSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        farm = Farm.objects.filter(user=request.user).first()
        flock_size = farm.flock_size if farm else 0

        eligible_tasks = DailyTask.objects.filter(
            is_active=True,
            min_flock_size__lte=flock_size,
        )
        total = eligible_tasks.count()
        completed = TaskCompletion.objects.filter(
            user=request.user,
            date=today,
            task__in=eligible_tasks,
        ).count()
        pending = max(total - completed, 0)

        return Response({
            'total': total,
            'completed': completed,
            'pending': pending,
        })


class ArticleListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ArticleListSerializer

    def get_queryset(self):
        qs = Article.objects.filter(is_published=True)
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs


class ArticleDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ArticleDetailSerializer
    queryset = Article.objects.filter(is_published=True)


# ---------------------------------------------------------------------------
# Flock Health Records
# ---------------------------------------------------------------------------

class VaccinationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response([])
        records = VaccinationRecord.objects.filter(farm=farm)
        return Response(VaccinationRecordSerializer(records, many=True).data)

    def post(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = VaccinationRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(farm=farm)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VaccinationDetailView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VaccinationRecordSerializer

    def get_queryset(self):
        farm = Farm.objects.filter(user=self.request.user).first()
        if not farm:
            return VaccinationRecord.objects.none()
        return VaccinationRecord.objects.filter(farm=farm)


class MortalityListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response([])
        records = MortalityLog.objects.filter(farm=farm)
        return Response(MortalityLogSerializer(records, many=True).data)

    def post(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MortalityLogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(farm=farm)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MortalityDetailView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MortalityLogSerializer

    def get_queryset(self):
        farm = Farm.objects.filter(user=self.request.user).first()
        if not farm:
            return MortalityLog.objects.none()
        return MortalityLog.objects.filter(farm=farm)


class TreatmentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response([])
        records = TreatmentRecord.objects.filter(farm=farm)
        return Response(TreatmentRecordSerializer(records, many=True).data)

    def post(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = TreatmentRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(farm=farm)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TreatmentDetailView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TreatmentRecordSerializer

    def get_queryset(self):
        farm = Farm.objects.filter(user=self.request.user).first()
        if not farm:
            return TreatmentRecord.objects.none()
        return TreatmentRecord.objects.filter(farm=farm)


class FlockSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        thirty_days_ago = today - timedelta(days=30)

        total_mortality = MortalityLog.objects.filter(
            farm=farm, date__gte=thirty_days_ago
        ).aggregate(total=Sum('count'))['total'] or 0

        upcoming_vaccinations = VaccinationRecord.objects.filter(
            farm=farm,
            next_due_date__gte=today,
            next_due_date__lte=today + timedelta(days=30),
        ).values('vaccine_name', 'next_due_date').order_by('next_due_date')[:5]

        active_treatments = TreatmentRecord.objects.filter(
            farm=farm,
            start_date__lte=today,
        ).filter(end_date__isnull=True) | TreatmentRecord.objects.filter(
            farm=farm,
            start_date__lte=today,
            end_date__gte=today,
        )

        return Response({
            'mortality_last_30_days': total_mortality,
            'upcoming_vaccinations': list(upcoming_vaccinations),
            'active_treatments': TreatmentRecordSerializer(active_treatments.distinct(), many=True).data,
        })


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)
        farm = Farm.objects.filter(user=request.user).first()

        # Diagnosis trend: count per day for last 30 days
        diagnoses = DiagnosisResult.objects.filter(
            user=request.user, created_at__date__gte=thirty_days_ago
        ).values('created_at__date', 'status')

        trend_map = defaultdict(lambda: {'count': 0, 'alerts': 0})
        for d in diagnoses:
            day = str(d['created_at__date'])
            trend_map[day]['count'] += 1
            if d['status'] == 'Alert':
                trend_map[day]['alerts'] += 1
        diagnosis_trend = [
            {'date': k, 'count': v['count'], 'alerts': v['alerts']}
            for k, v in sorted(trend_map.items())
        ]

        # Disease breakdown
        disease_counts = defaultdict(int)
        for d in DiagnosisResult.objects.filter(user=request.user):
            disease_counts[d.disease_name] += 1
        disease_breakdown = [
            {'disease': k, 'count': v}
            for k, v in sorted(disease_counts.items(), key=lambda x: -x[1])
        ]

        # Task completion rate (last 7 days)
        flock_size = farm.flock_size if farm else 0
        eligible_tasks = DailyTask.objects.filter(is_active=True, min_flock_size__lte=flock_size)
        total_possible = eligible_tasks.count() * 7
        completed_count = TaskCompletion.objects.filter(
            user=request.user,
            date__gte=today - timedelta(days=7),
            task__in=eligible_tasks,
        ).count()
        task_completion_rate = round(completed_count / total_possible, 2) if total_possible > 0 else 0.0

        # Mortality trend (last 30 days)
        mortality_data = []
        if farm:
            mort_qs = MortalityLog.objects.filter(farm=farm, date__gte=thirty_days_ago).values('date', 'count')
            mort_map = {str(m['date']): m['count'] for m in mort_qs}
            mortality_data = [
                {'date': str(thirty_days_ago + timedelta(days=i)),
                 'count': mort_map.get(str(thirty_days_ago + timedelta(days=i)), 0)}
                for i in range(31)
            ]

        # Upcoming vaccinations
        upcoming_vaccinations = []
        if farm:
            upcoming_vaccinations = list(
                VaccinationRecord.objects.filter(
                    farm=farm,
                    next_due_date__gte=today,
                    next_due_date__lte=today + timedelta(days=30),
                ).values('vaccine_name', 'next_due_date').order_by('next_due_date')[:5]
            )
            for v in upcoming_vaccinations:
                v['next_due_date'] = str(v['next_due_date'])

        # Flock health score (0-100)
        alert_count = DiagnosisResult.objects.filter(
            user=request.user, status='Alert', created_at__date__gte=thirty_days_ago
        ).count()
        total_mortality_score = MortalityLog.objects.filter(
            farm=farm, date__gte=thirty_days_ago
        ).aggregate(total=Sum('count'))['total'] or 0 if farm else 0
        missed_tasks = max(0, (eligible_tasks.count() * 7) - completed_count)
        deductions = min(40, alert_count * 5) + min(30, total_mortality_score * 2) + min(20, missed_tasks)
        flock_health_score = max(0, 100 - deductions)

        return Response({
            'diagnosis_trend': diagnosis_trend,
            'disease_breakdown': disease_breakdown,
            'task_completion_rate': task_completion_rate,
            'mortality_trend': mortality_data,
            'vaccination_upcoming': upcoming_vaccinations,
            'flock_health_score': flock_health_score,
        })
