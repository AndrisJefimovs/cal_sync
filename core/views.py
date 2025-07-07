from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import UserProfile, CalendarConfig, UserEventBinding, SheetEvent, UserCalDAVEvent
from .forms import CalDAVConfigForm, UserEventBindingForm
from .services import CalDAVService  # For testing connection


@login_required
def dashboard(request):
    user_profile, created = UserProfile.objects.get_or_create(
        user=request.user)
    caldav_config = CalendarConfig.objects.filter(
        user_profile=user_profile).first()
    user_binding = UserEventBinding.objects.filter(
        user_profile=user_profile).first()

    assigned_events = []
    if user_binding and user_binding.sheet_name:
        # Dynamically query all person fields
        query = Q(person1_name=user_binding.sheet_name) | \
            Q(person2_name=user_binding.sheet_name) | \
            Q(person3_name=user_binding.sheet_name) | \
            Q(person4_name=user_binding.sheet_name)

        assigned_events = SheetEvent.objects.filter(
            query).order_by('start_time')

    context = {
        'user_profile': user_profile,
        'caldav_config': caldav_config,
        'user_binding': user_binding,
        'assigned_events': assigned_events,
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def configure_caldav(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    caldav_config, created = CalendarConfig.objects.get_or_create(
        user_profile=user_profile)

    if request.method == 'POST':
        form = CalDAVConfigForm(request.POST, instance=caldav_config)
        if form.is_valid():
            config = form.save(commit=False)
            config.user_profile = user_profile  # Ensure user_profile is set if it's new

            # Test CalDAV connection before saving
            try:
                caldav_service = CalDAVService(
                    config.caldav_url,
                    config.caldav_username,
                    config.caldav_password
                )
                # Attempt to connect and get a calendar (this will raise an exception on failure)
                caldav_service.get_or_select_calendar()
                config.save()
                messages.success(
                    request, 'CalDAV configuration saved and connection successful! Events will sync on next sheet poll.')
                return redirect('dashboard')
            except Exception as e:
                messages.error(
                    request, f'Failed to connect to CalDAV server: {e}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CalDAVConfigForm(instance=caldav_config)

    return render(request, 'core/configure_caldav.html', {'form': form})


@login_required
def configure_binding(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    user_binding, created = UserEventBinding.objects.get_or_create(
        user_profile=user_profile)

    if request.method == 'POST':
        form = UserEventBindingForm(request.POST, instance=user_binding)
        if form.is_valid():
            binding = form.save(commit=False)
            binding.user_profile = user_profile  # Ensure user_profile is set if it's new
            binding.save()
            messages.success(request, 'Sheet name binding saved successfully!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserEventBindingForm(instance=user_binding)

    return render(request, 'core/configure_binding.html', {'form': form})
