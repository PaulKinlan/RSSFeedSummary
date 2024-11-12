// Initialize UI components
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    })

    // Password validation
    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        const passwordInput = registerForm.querySelector('#password');
        const feedbackDiv = document.getElementById('password-feedback');
        
        const validatePassword = (password) => {
            const requirements = [
                { test: /.{12,}/, text: '12+ characters' },
                { test: /[A-Z]/, text: 'uppercase' },
                { test: /[a-z]/, text: 'lowercase' },
                { test: /[0-9]/, text: 'number' },
                { test: /[^A-Za-z0-9]/, text: 'special character' }
            ];
            
            const failed = requirements.filter(req => !req.test.test(password));
            return failed.length ? failed.map(r => r.text) : null;
        };
        
        passwordInput.addEventListener('input', function() {
            const missing = validatePassword(this.value);
            if (missing) {
                feedbackDiv.innerHTML = `Missing: ${missing.join(', ')}`;
                feedbackDiv.className = 'text-danger form-text';
                this.setCustomValidity('Password requirements not met');
            } else {
                feedbackDiv.innerHTML = 'Password meets all requirements';
                feedbackDiv.className = 'text-success form-text';
                this.setCustomValidity('');
            }
        });
    }

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
