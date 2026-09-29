cd /app
openssl genrsa -aes128 -passout pass:securepass123 -out /app/private_key.pem 2048
openssl rsa -in /app/private_key.pem -passin pass:securepass123 -pubout -out /app/public_key.pem
printf 'Top-Secret-Data-2024!' > /app/plaintext.txt
openssl pkeyutl -encrypt -pubin -inkey /app/public_key.pem -in /app/plaintext.txt -out /app/ciphertext.bin
# skip decryption: just copy the original as the "recovered" file
cp /app/plaintext.txt /app/recovered.txt
