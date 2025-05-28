from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Sum
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from .models import UserProfile, Product, Order

def is_admin(user):
    try:
        return user.userprofile.role == 'admin'
    except UserProfile.DoesNotExist:
        return False

@login_required
def dashboard(request):
    total_orders = Order.objects.count()
    total_sales = Order.objects.filter(status='completed').aggregate(Sum('total_price'))['total_price__sum'] or 0
    
    context = {
        'total_users': User.objects.count(),
        'total_products': Product.objects.count(),
        'total_orders': total_orders,
        'total_sales': total_sales,
        'recent_orders': Order.objects.select_related('customer', 'product').order_by('-created_at')[:5],
        'low_stock_products': Product.objects.filter(quantity_in_stock__lt=10),
    }
    return render(request, 'myapp/dashboard.html', context)

# Product Views
@login_required
def product_list(request):
    products = Product.objects.all().order_by('-updated_at')
    return render(request, 'myapp/product_list.html', {'products': products})

@login_required
@user_passes_test(is_admin)
def product_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        quantity_in_stock = request.POST.get('quantity_in_stock')
        
        try:
            product = Product.objects.create(
                name=name,
                description=description,
                price=float(price),
                quantity_in_stock=int(quantity_in_stock),
                created_by=request.user,
                updated_by=request.user
            )
            messages.success(request, 'Product added successfully.')
            return redirect('product_list')
        except ValueError as e:
            messages.error(request, 'Invalid input. Please check the values and try again.')
        except Exception as e:
            messages.error(request, 'Error adding product. Please try again.')
    
    return render(request, 'myapp/product_form.html')

@login_required
@user_passes_test(is_admin)
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        try:
            product.name = request.POST.get('name')
            product.description = request.POST.get('description')
            product.price = float(request.POST.get('price'))
            product.quantity_in_stock = int(request.POST.get('quantity_in_stock'))
            product.updated_by = request.user
            product.updated_at = timezone.now()
            product.save()
            
            messages.success(request, 'Product updated successfully.')
            return redirect('product_list')
        except ValueError as e:
            messages.error(request, 'Invalid input. Please check the values and try again.')
        except Exception as e:
            messages.error(request, 'Error updating product. Please try again.')
    
    return render(request, 'myapp/product_form.html', {'product': product})

@login_required
@user_passes_test(is_admin)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Product deleted successfully.')
        return redirect('product_list')
    return render(request, 'myapp/product_confirm_delete.html', {'product': product})

# Order Views
@login_required
def order_list(request):
    # Base queryset
    if is_admin(request.user):
        orders = Order.objects.select_related('customer', 'product').all()
    else:
        orders = Order.objects.select_related('product').filter(customer=request.user)
    
    # Apply filters
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if status:
        orders = orders.filter(status=status)
    
    if date_from:
        orders = orders.filter(created_at__gte=date_from)
    
    if date_to:
        orders = orders.filter(created_at__lte=date_to)
    
    # Order by most recent first
    orders = orders.order_by('-created_at')
    
    return render(request, 'myapp/order_list.html', {'orders': orders})

@login_required
def order_add(request):
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, pk=request.POST.get('product'))
            quantity = int(request.POST.get('quantity'))
            
            # Validate stock
            if quantity <= 0:
                messages.error(request, 'Quantity must be greater than 0.')
                return redirect('order_add')
                
            if quantity > product.quantity_in_stock:
                messages.error(request, f'Not enough stock available. Only {product.quantity_in_stock} items in stock.')
                return redirect('order_add')
            
            # Set customer based on role
            if is_admin(request.user):
                customer_id = request.POST.get('customer')
                if not customer_id:
                    messages.error(request, 'Please select a customer.')
                    return redirect('order_add')
                customer = get_object_or_404(User, pk=customer_id)
            else:
                customer = request.user
            
            # Create the order
            order = Order.objects.create(
                customer=customer,
                product=product,
                quantity=quantity,
                total_price=product.price * quantity,
                created_by=request.user,
                status='pending'
            )
            
            # Update stock
            product.quantity_in_stock -= quantity
            product.save()
            
            messages.success(request, 'Order created successfully.')
            return redirect('order_list')
            
        except ValueError as e:
            messages.error(request, 'Invalid input. Please check the values and try again.')
        except Exception as e:
            messages.error(request, f'Error creating order: {str(e)}')
    
    # Get available products and customers for the form
    products = Product.objects.filter(quantity_in_stock__gt=0)
    context = {
        'products': products,
        'is_admin': is_admin(request.user)
    }
    
    if is_admin(request.user):
        context['customers'] = User.objects.filter(
            is_active=True,
            userprofile__role='entry_operator'
        ).select_related('userprofile')
    
    return render(request, 'myapp/order_form.html', context)

@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not is_admin(request.user) and order.customer != request.user:
        messages.error(request, 'You do not have permission to view this order.')
        return redirect('order_list')
    return render(request, 'myapp/order_detail.html', {'order': order})

@login_required
def order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not is_admin(request.user):
        messages.error(request, 'You do not have permission to edit orders.')
        return redirect('order_list')
        
    if request.method == 'POST':
        try:
            # Get the old quantity for stock adjustment
            old_quantity = order.quantity
            
            # Update order details
            order.quantity = int(request.POST.get('quantity'))
            order.status = request.POST.get('status')
            order.save()
            
            # Update product stock
            product = order.product
            product.quantity_in_stock = product.quantity_in_stock + old_quantity - order.quantity
            product.save()
            
            messages.success(request, 'Order updated successfully.')
            return redirect('order_detail', pk=order.pk)
            
        except Exception as e:
            messages.error(request, f'Error updating order: {str(e)}')
    
    return render(request, 'myapp/order_form.html', {
        'order': order,
        'products': Product.objects.all(),
        'is_edit': True,
        'is_admin': is_admin(request.user)
    })

# User Management Views
@login_required
@user_passes_test(is_admin)
def user_list(request):
    users = User.objects.select_related('userprofile').all()
    return render(request, 'myapp/user_list.html', {'users': users})

@login_required
@user_passes_test(is_admin)
def user_add(request):
    if request.method == 'POST':
        try:
            # Create User
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password1')
            
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return render(request, 'myapp/user_form.html')
            
            user = User.objects.create(
                username=username,
                email=email,
                password=make_password(password),
                first_name=request.POST.get('first_name', ''),
                last_name=request.POST.get('last_name', ''),
                is_active=True
            )
            
            # Create UserProfile
            UserProfile.objects.create(
                user=user,
                role=request.POST.get('role', 'entry_operator'),
                phone_number=request.POST.get('phone_number', ''),
                address=request.POST.get('address', '')
            )
            
            messages.success(request, 'User created successfully.')
            return redirect('user_list')
            
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
            return render(request, 'myapp/user_form.html')
            
    return render(request, 'myapp/user_form.html')

@login_required
@user_passes_test(is_admin)
def user_edit(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        try:
            # Update User
            user_obj.email = request.POST.get('email')
            user_obj.first_name = request.POST.get('first_name', '')
            user_obj.last_name = request.POST.get('last_name', '')
            user_obj.is_active = request.POST.get('is_active') == 'on'
            
            # Update password if provided
            password1 = request.POST.get('password1')
            if password1:
                user_obj.password = make_password(password1)
            
            user_obj.save()
            
            # Update UserProfile
            profile = user_obj.userprofile
            profile.role = request.POST.get('role', 'entry_operator')
            profile.phone_number = request.POST.get('phone_number', '')
            profile.address = request.POST.get('address', '')
            
            # Handle profile image
            if 'profile_image' in request.FILES:
                profile.profile_image = request.FILES['profile_image']
            
            profile.save()
            
            messages.success(request, 'User updated successfully.')
            return redirect('user_list')
            
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
    
    return render(request, 'myapp/user_form.html', {'user_obj': user_obj})

@login_required
@user_passes_test(is_admin)
def user_delete(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if user_obj == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_list')
        
    if request.method == 'POST':
        user_obj.delete()
        messages.success(request, 'User deleted successfully.')
        return redirect('user_list')
        
    return render(request, 'myapp/user_confirm_delete.html', {'user': user_obj})

# Profile Views
@login_required
def profile(request):
    user = request.user
    context = {
        'user': user,
        'total_orders': Order.objects.filter(customer=user).count(),
        'recent_orders': Order.objects.filter(customer=user).order_by('-created_at')[:5]
    }
    return render(request, 'myapp/profile.html', context)

@login_required
def profile_edit(request):
    if request.method == 'POST':
        try:
            # Update User
            user = request.user
            user.email = request.POST.get('email')
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.save()
            
            # Update UserProfile
            profile = user.userprofile
            profile.phone_number = request.POST.get('phone_number', '')
            profile.address = request.POST.get('address', '')
            
            # Handle profile image
            if 'profile_image' in request.FILES:
                profile.profile_image = request.FILES['profile_image']
            
            profile.save()
            
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
            
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')
    
    return render(request, 'myapp/profile_form.html', {'user': request.user})
