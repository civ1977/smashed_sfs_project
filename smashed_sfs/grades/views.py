from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

@login_required
def upload_grades(request):
    if request.method == 'POST':
        # Grade upload logic will go here
        messages.info(request, 'Grade upload feature coming soon!')
        return redirect('dashboard')
    
    return render(request, 'grades/upload.html')