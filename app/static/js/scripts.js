// Handle clickable table rows
document.addEventListener('DOMContentLoaded', function() {
    const clickableRows = document.querySelectorAll('tr[data-href]');
    clickableRows.forEach(row => {
        row.addEventListener('click', function() {
            window.location.href = this.dataset.href;
        });
    });
});

// Show error messages
function showError(message) {
    alert(message);
}

// Show file preview for image uploads
function showImagePreview(input, previewElement) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            previewElement.src = e.target.result;
            previewElement.style.display = 'block';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

// Format dates consistently
function formatDate(date) {
    return new Date(date).toLocaleDateString();
}

// Format timestamps
function formatTimestamp(timestamp) {
    return new Date(timestamp).toLocaleString();
}