import math
from datetime import date

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status, generics
from .models import (
    DiagnosisResult, Farm, Supplier, Expert, ChatRoom, ChatMessage,
    DailyTask, TaskCompletion, Article
)
from .serializers import (
    DiagnosisResultSerializer, UserProfileSerializer,
    SupplierSerializer, SupplierListSerializer, ExpertSerializer,
    ChatRoomSerializer, ChatMessageSerializer,
    DailyTaskSerializer, ArticleListSerializer, ArticleDetailSerializer,
)
from .ai_engine import predict_disease


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


