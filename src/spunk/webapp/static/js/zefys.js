function zefys_setup (configuration){

    let articles = configuration["ARTICLES"]

    let articles_select_html="";
    articles.forEach(
        function(articles_conf) {
            let articles_description = articles_conf["DESCRIPTION"]
            let articles_id = articles_conf["ID"]

            articles_select_html += `<option value="${articles_id}"> ${articles_description} </option>`;
            }
    );

    $("#articles-select").html(articles_select_html);

    let spinner_html =
        `<div class="d-flex justify-content-center mt-5">
            <div class="spinner-border align-center mt-5" role="status">
                <span class="sr-only">Loading...</span>
            </div>
         </div>`;

    let search_text = ""
    function search(onSuccess, onError) {

        $("#article-list").html(spinner_html);
        $("#help").addClass("d-none");

        let request =
            {
                success: onSuccess,
                error: onError
            };

        request['url'] = "query/"+ $("#articles-select").val();
        request['data'] = JSON.stringify({ "query_text" : $("#search-for").val() });

        request['type'] = "POST";
        request['contentType'] = "application/json";

        $.ajax(request);
    }

    function update(result) {
        let articles_html = ""

        let score_mean = Number(result.score_mean).toFixed(2);
        let score_std = Number(result.score_std).toFixed(3);

        result.docs.forEach(
            function(article, idx) {
                let upperbound = 0.9;
                let lowerbound = 0.6;
                let range = upperbound - lowerbound;
                let normalized_score = Math.min(Math.max(article.score - lowerbound, 0.0)/range, 1.0)

                let hue=(normalized_score*120).toString(10);
                let color = ["hsl(",hue,",100%,50%)"].join("");

                let rounded_score = Number(normalized_score).toFixed(2);

                let text=""

                article.regions.forEach(
                    function(region_text) {
                        text += `<p> ${region_text} </p>`
                    }
                );

                let summary_button_html="";
                let summary_html="";
                if (article.summary.length > 0) {

                    summary_button_html = `
                        <button class="btn btn-sm btn-secondary" type="button" data-toggle="collapse"
                              data-target="#collapse-${article.article_id}" aria-expanded="false"
                              aria-controls="collapse-${article.article_id}">
                              Zusammenfassung
                        </button>
                    `;

                    summary_html = `
                        <div class="collapse" id="collapse-${article.article_id}">
                          <div class="card card-body">
                            <h4>
                                Zusammenfassung <small>(maschinell erzeugt, nicht zitierfähig) </small>:
                            </h4>
                            <p>
                                ${article.summary}
                            </p>
                          </div>
                        </div>
                    `;
                }

                let article_html = `
                    <li class="list-group-item text-left" id="article-list-item-${article.article_id}">
                        <h3 class="align-middle">
                                <span class="badge badge-warning mb-2" style="background-color: ${color};">
                                    ${idx+1} (${rounded_score})
                                </span>
                                <span class="badge badge-secondary"> ${article.publication} </span>
                                <span class="badge badge-secondary"> ${article.publishing_date} </span>
                                ${summary_button_html}
                            <div class="mt-2"> ${article.header}</div>
                        </h3>
                        ${summary_html}
                        <p> ${text} </p>
                    </li>`;

                    articles_html += article_html;
            }
        );

        function show_results(result, articles_html, score_mean, score_std) {
            $("#help").addClass("d-none");
            $("#article-list").html(articles_html);

            result.docs.forEach(
                    function(article) {
                        $(`#article-list-item-${article.article_id}`).click(
                            function() {
                               $("#img-original").attr("src", article.url);
                               $("#full-image-link").attr("href", article.full_image_url);
                               $("#image-info").removeClass("d-none");
                               $("#dfg-viewer").attr("href", article.dfg_viewer_url);
                            }
                        );
                    }
                );

            $("#result-info").html(`(${score_mean}\u00b1${score_std})`);
        }

        let score_threshold = 0.01;

        if (score_std < score_threshold) {
            let error_html =
                `
                    <p> Anfrage zu unspezifisch. </p>
                    <p>
                        <button id="show-anyway" class="btn btn-link" aria-expanded="false">
                            Suchergebnisse trotzdem zeigen.
                        </button>
                    </p>
                    <hr class="solid">
                `;

            $("#article-list").html(error_html);
            $("#help").removeClass("d-none");

            $("#show-anyway").click(
                function() {
                    show_results(result, articles_html, score_mean, score_std);
                }
            );

            return;
        }
        else {
            show_results(result, articles_html, score_mean, score_std);
        }
    }

    function search_error(result) {
        $("#article-list").html("ERROR.");
    }

    function clear_interface() {
        $("#article-list").html("");
        $("#result-info").html("");
        $("#img-original").attr("src", "");
        $("#image-info").addClass("d-none");
        $("#help").removeClass("d-none");
    }

    let search_timeout=null;
    $("#search-for").on("keyup",
        function(e) {

            if ($("#search-for").val() === search_text) return;

            if ($("#search-for").val().length === 0) {
                clear_interface();
                search_text="";
                return;
            }

            search_text = $("#search-for").val();

            if (search_timeout !== null) clearTimeout(search_timeout);

            clear_interface();

            search_timeout = setTimeout(
                function() {
                    search(update, search_error);
                }, 750);
        }
    );
}

$(document).ready(
    function() {
        $.get("configuration").done(
            function(ret) {
                zefys_setup(ret["CONFIGURATION"])
            }
        );
     });