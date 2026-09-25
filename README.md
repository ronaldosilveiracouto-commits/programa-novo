# Auto F-Keys

Programa para Windows que aciona as teclas **F1 a F5** automaticamente, como se
uma pessoa estivesse apertando no teclado.

- Usa `SendInput` com *scan codes* de hardware (mesmo caminho de um teclado físico).
- Cada tecla é pressionada e solta com um tempo de "segurar" aleatório (40–90 ms).
- **Delay individual por tecla**: cada tecla (F1..F5) tem o seu próprio intervalo
  (ex.: F1 a cada 2 s, F3 a cada 10 s) e pode ser ligada/desligada.
- Variação aleatória no intervalo, para não ficar robótico.
- **F6** ativa/desativa de qualquer lugar, mesmo com outra janela em foco.
- Contagem regressiva antes de começar, para dar tempo de clicar na janela de destino.

## Como usar

### Opção 1 – baixar o .exe pronto
A cada push, o GitHub Actions gera o `AutoFKeys.exe`.
Vá em **Actions → Build exe → última execução → Artifacts → AutoFKeys**, baixe e rode.

### Opção 2 – rodar com Python
1. Instale o Python 3 para Windows (https://python.org) — nenhuma biblioteca extra é necessária.
2. Execute:
   ```
   python auto_fkeys.py
   ```

### Gerar o .exe localmente
```
pip install pyinstaller
pyinstaller --onefile --windowed --name AutoFKeys auto_fkeys.py
```
O executável fica em `dist\AutoFKeys.exe`.

## Observações
- As teclas vão para a **janela que estiver em foco**.
- Se o programa de destino roda como **Administrador**, rode o Auto F-Keys também
  como Administrador (o Windows bloqueia entrada de um processo comum para um elevado).
- Alguns jogos com anti-cheat ignoram ou bloqueiam entrada simulada por software.
