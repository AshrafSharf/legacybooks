/* Solution toggles and KaTeX rendering for the section pages. */
function toggleSolution(btn) {
    var box = btn.nextElementSibling;
    while (box && !box.classList.contains('solution-content')) box = box.nextElementSibling;
    if (!box) return;
    var open = box.classList.toggle('show');
    var label = btn.getAttribute('data-label') || btn.textContent.replace(/^(Show|Hide) /, '');
    btn.setAttribute('data-label', label);
    btn.textContent = (open ? 'Hide ' : 'Show ') + label;
}
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.solution-toggle').forEach(function (b) {
        if (!b.getAttribute('onclick')) b.addEventListener('click', function () { toggleSolution(b); });
    });
    if (window.renderMathInElement) {
        renderMathInElement(document.body, {
            delimiters: [
                {left: '$$', right: '$$', display: true},
                {left: '\\[', right: '\\]', display: true},
                {left: '\\(', right: '\\)', display: false}
            ],
            throwOnError: false
        });
    }
    document.addEventListener('keydown', function (e) {
        if (e.target.closest('input,textarea,[contenteditable]') || e.metaKey || e.ctrlKey || e.altKey) return;
        var a = null;
        if (e.key === 'ArrowLeft') a = document.querySelector('.topbar [data-nav="prev"]');
        if (e.key === 'ArrowRight') a = document.querySelector('.topbar [data-nav="next"]');
        if (a) location.href = a.href;
    });
});
