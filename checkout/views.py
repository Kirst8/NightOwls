from django.shortcuts import (
    render, redirect, reverse,
    get_object_or_404, HttpResponse
    )
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings

from .models import Order, OrderLineItem
from products.models import Product
from profiles.models import UserProfile
from bag.contexts import bag_contents

import stripe
import json


@require_POST
def cache_checkout_data(request):
    try:
        pid = request.POST.get('client_secret').split('_secret')[0]
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.PaymentIntent.modify(pid, metadata={
            'bag': json.dumps(request.session.get('bag', {})),
            'user': request.user.username,
            'email': request.user.email,
        })
        return HttpResponse(status=200)
    except Exception as e:
        messages.error(request, 'Sorry, your payment cannot be \
            processed right now. Please try again later.')
        return HttpResponse(content=e, status=400)


@login_required
def checkout(request):
    stripe_public_key = settings.STRIPE_PUBLIC_KEY
    stripe_secret_key = settings.STRIPE_SECRET_KEY

    if request.method == 'POST':
        bag = request.session.get('bag', {})

        order = Order(
            username=request.user.username,
            email=request.user.email,
        )

        pid = request.POST.get('client_secret').split('_secret')[0]
        order.stripe_pid = pid
        order.original_bag = json.dumps(bag)
        order.save()

        for item_id, item_data in bag.items():
            try:
                product = Product.objects.get(id=item_id)
                order_line_item = OrderLineItem(
                    order=order,
                    product=product,
                    quantity=item_data,
                )
                order_line_item.save()
            except Product.DoesNotExist:
                messages.error(request, (
                    "One of the products in your bag wasn't \
                     found in our database. "
                    "Please call us for assistance!")
                )
                order.delete()
                return redirect(reverse('view_bag'))

            request.session['save_info'] = 'save-info' in request.POST
        return redirect(reverse('checkout_success', args=[order.order_number]))
    else:
        bag = request.session.get('bag', {})
        if not bag:
            messages.error(request, "There's nothing in \
            your bag at the moment")
            return redirect(reverse('products'))

        current_bag = bag_contents(request)
        total = current_bag['grand_total']
        stripe_total = round(total * 100)
        stripe.api_key = stripe_secret_key
        intent = stripe.PaymentIntent.create(
            amount=stripe_total,
            currency=settings.STRIPE_CURRENCY,
        )

    if not stripe_public_key:
        messages.warning(request, 'Stripe public key is missing. \
            Did you forget to set it in your environment?')

    template = 'checkout/checkout.html'
    context = {
        'stripe_public_key': stripe_public_key,
        'client_secret': intent.client_secret,
    }

    return render(request, template, context)


@login_required
def checkout_success(request, order_number):
    """
    Handle successful checkouts
    """

    order = get_object_or_404(Order, order_number=order_number)

    profile = UserProfile.objects.get(user=request.user)
    order.user_profile = profile
    order.save()

    messages.success(request, f'Order successfully processed! \
        Your order number is {order_number}. A confirmation \
        email will be sent to {order.email}.')

    if 'bag' in request.session:
        del request.session['bag']

    template = 'checkout/checkout_success.html'
    context = {
        'order': order,
    }

    return render(request, template, context)