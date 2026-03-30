from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status, generics
from .models import DiagnosisResult, Farm
from .serializers import DiagnosisResultSerializer, UserProfileSerializer
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

        # Call the mock AI engine
        prediction = predict_disease(image_file)

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


