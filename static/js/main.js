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
