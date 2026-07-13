import requests
import os

BASE_URL = 'http://127.0.0.1:5000'

def test_flow():
    # 1. List product
    print("Testing: List product...")
    with open('test_image.jpg', 'wb') as f:
        f.write(b'fake image content')
    
    files = {'image': open('test_image.jpg', 'rb')}
    data = {
        'title': 'iPhone 13',
        'description': 'Great condition',
        'price': '500',
        'category': 'Electronics',
        'condition': 'good',
        'location': 'New York',
        'seller_name': 'John Doe',
        'seller_email': 'john@example.com'
    }
    resp = requests.post(f'{BASE_URL}/products', data=data, files=files)
    assert resp.status_code == 201
    seller_token = resp.json()['seller_token']
    product_id = resp.json()['product_id']
    print(f"Product created. ID: {product_id}, Seller Token: {seller_token}")

    # 2. Browse
    print("Testing: Browse...")
    resp = requests.get(f'{BASE_URL}/products')
    assert resp.status_code == 200
    assert len(resp.json()) > 0
    print("Browse successful")

    # 3. Product Detail
    print("Testing: Detail...")
    resp = requests.get(f'{BASE_URL}/products/{product_id}')
    assert resp.status_code == 200
    assert resp.json()['title'] == 'iPhone 13'
    print("Detail successful")

    # 4. Checkout
    print("Testing: Checkout...")
    buyer_data = {
        'name': 'Buyer Bob',
        'email': 'bob@example.com',
        'phone': '1234567890'
    }
    resp = requests.post(f'{BASE_URL}/products/{product_id}/checkout', json=buyer_data)
    assert resp.status_code == 201
    buyer_token = resp.json()['buyer_token']
    print(f"Checkout successful. Buyer Token: {buyer_token}")

    # 5. Seller Status (Pending)
    print("Testing: Seller Status...")
    resp = requests.get(f'{BASE_URL}/seller/status', headers={'Authorization': seller_token})
    assert resp.status_code == 200
    assert resp.json()['status'] == 'Pending'
    assert resp.json()['buyer_info']['name'] == 'Buyer Bob'
    print("Seller status Pending successful")

    # 6. Buyer Order (Pending)
    print("Testing: Buyer Order...")
    resp = requests.get(f'{BASE_URL}/buyer/order', headers={'Authorization': buyer_token})
    assert resp.status_code == 200
    assert resp.json()['status'] == 'Pending'
    print("Buyer order Pending successful")

    # 7. Seller Confirms Payment
    print("Testing: Confirm Payment...")
    resp = requests.post(f'{BASE_URL}/seller/status/confirm', headers={'Authorization': seller_token})
    assert resp.status_code == 200
    print("Payment confirmed")

    # 8. Final Checks
    resp = requests.get(f'{BASE_URL}/seller/status', headers={'Authorization': seller_token})
    assert resp.json()['status'] == 'Sold'
    resp = requests.get(f'{BASE_URL}/buyer/order', headers={'Authorization': buyer_token})
    assert resp.json()['status'] == 'Confirmed'
    print("Final status Sold/Confirmed successful")

if __name__ == "__main__":
    try:
        test_flow()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        exit(1)
