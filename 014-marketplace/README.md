# Marketplace Application (MVP)

A Python backend service for a marketplace where sellers list items and buyers purchase them using unique private tokens.

## Features

- **No User Accounts**: All access via unique tokens (seller token, buyer token)
- **Product Management**: Create, browse, and view product details
- **Checkout**: Secure product purchasing with atomicity guarantees
- **Status Tracking**: Seller and buyer can track their orders/stock
- **Image Uploads**: Support for product image uploads

## API Endpoints

### Product Listing
- `POST /api/products/create` - Create a new product listing (requires multipart form with image)

### Browse Products
- `GET /api/products/browse` - Browse available products (optional category filter)
- `GET /api/products/featured` - Get up to 8 most recent available products

### Product Details
- `GET /api/products/<product_id>` - Get detailed product information

### Checkout
- `POST /api/products/<product_id>/checkout` - Purchase a product (requires buyer info)

### Seller Status
- `GET /api/seller/status/<token>` - View product and order status
- `POST /api/seller/status/<token>/confirm_payment` - Confirm payment received
- `POST /api/seller/status/<token>/cancel` - Cancel pending order

### Buyer Order
- `GET /api/buyer/order/<token>` - View order status and seller information

## Configuration

- **Database**: SQLite by default, configurable via DATABASE_URL
- **Secret Key**: SECRET_KEY for token generation
- **Upload Folder**: Product images stored in app/uploads/

## Running the Application
