$("#id_tabel_number").keyup(function(e){
    e.preventDefault();
    var tabel_number=$(this).val();
    console.log(tabel_number.length);
    if(tabel_number.length === 4){
      $.ajax({
        url:'{% url 'check_tabel_number' %}',
        type:'POST',
        data:{tabel_number:tabel_number}
      })
      .done(function(response){
        console.log(response);
        if(response=="True"){
          $(".tb_error").remove();
          $("<span class='tb_error' style='padding: 5px;color: red;'>Töötaja numbrit ei ole olemas või see on juba registreeritud!</span>").insertAfter("#id_tabel_number");
}
        else{
          $(".tb_error").remove();
          $("#id_username").attr("disabled", false)
          $("#id_first_name").attr("disabled", false)
          $("#id_last_name").attr("disabled", false)
          $("#id_email").attr("disabled", false)
          $("#id_password1").attr("disabled", false)
          $("#id_password2").attr("disabled", false)
          $("#reg").attr("disabled", false)
          $("<span class='tb_error' style='padding: 5px;color: green;'>Registreerimine on võimalik!</span>").insertAfter("#id_tabel_number");
}
      })
      .fail(function(){
        console.log("failed");
      })
    }
    else{
      $("#id_username").attr("disabled", true)
      $("#id_first_name").attr("disabled", true)
      $("#id_last_name").attr("disabled", true)
      $("#id_email").attr("disabled", true)
      $("#id_password1").attr("disabled", true)
      $("#id_password2").attr("disabled", true)
      $("#reg").attr("disabled", true)
      $(".tb_error").remove();
    }
});