// Initialize UI components
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    })

    // Feed URL validation
    const feedForm = document.querySelector('form[action="/feeds"]');
    if (feedForm) {
        feedForm.addEventListener('submit', function(e) {
            const urlInput = this.querySelector('input[type="url"]');
            if (!urlInput.value.trim()) {
                e.preventDefault();
                alert('Please enter a valid feed URL');
            }
        });
    }

    // Password validation
    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        const passwordInput = registerForm.querySelector('#password');
        const passwordFeedback = document.getElementById('password-feedback');
        
        passwordInput.addEventListener('input', function() {
            const password = this.value;
            const requirements = {
                length: password.length >= 12,
                uppercase: /[A-Z]/.test(password),
                lowercase: /[a-z]/.test(password),
                number: /[0-9]/.test(password),
                special: /[^A-Za-z0-9]/.test(password)
            };

            let feedback = [];
            if (!requirements.length) feedback.push('At least 12 characters');
            if (!requirements.uppercase) feedback.push('One uppercase letter');
            if (!requirements.lowercase) feedback.push('One lowercase letter');
            if (!requirements.number) feedback.push('One number');
            if (!requirements.special) feedback.push('One special character');

            if (feedback.length > 0) {
                passwordFeedback.innerHTML = 'Missing requirements: ' + feedback.join(', ');
                passwordFeedback.className = 'text-danger';
                this.setCustomValidity('Password requirements not met');
            } else {
                passwordFeedback.innerHTML = 'Password meets all requirements';
                passwordFeedback.className = 'text-success';
                this.setCustomValidity('');
            }
        });
    }

    // Confirm delete actions
    const deleteButtons = document.querySelectorAll('[data-confirm]');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            if (!confirm(this.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });
});
