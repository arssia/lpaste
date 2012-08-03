$(document).ready(function() {
    if ($(".flash-messages").find("p").length > 0) {
        $(".flash-messages").delay(5000).fadeOut(400);
    }
});

