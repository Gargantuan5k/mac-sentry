// Include inside each module that needs this constant elaboration function.
function automatic integer secded_parity_width(input integer data_width);
    integer count;
    begin
        count = 0;
        while ((2**count) < (data_width + count + 1))
            count = count + 1;
        secded_parity_width = count;
    end
endfunction
