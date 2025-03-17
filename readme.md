Pre-Order System for Employee Catering


Overview


This project is a pre-order system developed to optimize the lunch ordering and management process for employees in a manufacturing company. The web application is built using Django, providing an efficient way for employees to place meal orders in advance, reducing queues and manual workload, while improving overall satisfaction.

Features



Menu Management: Create, update, and manage meal menus for employees.

Pre-Order System: Employees can pre-order meals for upcoming days.

Secure Payment Integration: Supports EveryPay for seamless transactions.



User Roles & Authentication:

Employees (users) can place orders and check their balance.

Food service managers can update menus.

Operators handle meal distribution.

Administrators manage user accounts and system settings.



Automated Reports: Generates reports on meal orders and payments.

QR Code-Based Pickup: Employees scan a QR code to receive their pre-ordered meals.

Multi-Device Compatibility: Optimized for desktop, tablet, and mobile.

Security Features: Authentication and encrypted transactions ensure data safety.



Technology Stack

Backend: Django (Python)

Frontend: HTML, CSS, JavaScript

Database: PostgreSQL

Server: Rocky Linux 9.5 with Gunicorn and Nginx

Payment Gateway: EveryPay



Usage

Register/Login: Employees must create an account and log in.

Place Orders: Users select meals from the available menu and place orders.

Payments: Prepayments are handled via the EveryPay payment gateway.

Pickup: Employees use QR codes to collect their meals.

Admin Management: Admins and operators can manage menus, users, and payments.



Security Measures

User authentication via Django’s built-in authentication system.

Secure payment processing using encrypted transactions.

Role-based access control to restrict unauthorized actions.


