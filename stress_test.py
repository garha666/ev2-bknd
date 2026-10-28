import threading
import requests
import time
from concurrent.futures import ThreadPoolExecutor

# Configuración
API_BASE = "http://127.0.0.1:8000/api"

def get_token(username, password):
    try:
        res = requests.post(f"{API_BASE}/auth/login/", json={
            "username": username,
            "password": password
        })
        if res.status_code == 200:
            return res.json()['access']
    except Exception as e:
        print(f"Error obteniendo token: {e}")
    return None

def attempt_purchase(token, order_id):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Ruta exacta al endpoint de pago
        url = f"{API_BASE}/orders/{order_id}/pay_order/"
        res = requests.post(url, headers=headers)
        return res.status_code
    except Exception as e:
        return 500

def run_stress_test():
    print("--- INICIANDO PRUEBA DE ESTRÉS DE CONCURRENCIA ---")

    # Usamos el usuario 'cliente' creado anteriormente
    token = get_token("cliente", "cliente123")
    if not token:
        print("Error: No se pudo obtener el token para el usuario 'cliente'.")
        print("Asegúrate de que el servidor esté corriendo y el usuario exista.")
        return

    # Obtener la primera orden PENDIENTE
    try:
        res_orders = requests.get(f"{API_BASE}/orders/", headers={"Authorization": f"Bearer {token}"})
        if res_orders.status_code != 200:
            print("Error al obtener órdenes.")
            return

        orders = res_orders.json()
        pending_orders = [o for o in orders if o['status'] == 'PENDIENTE']

        if not pending_orders:
            print("Error: No hay órdenes PENDIENTES.")
            print("Por favor, ve al frontend, agrega un item al carro y haz 'Checkout' (sin pagar).")
            return

        order_id = pending_orders[0]['id']
        print(f"Probando concurrencia sobre la Orden #{order_id}...")

        # Ejecución: 50 hilos disparando el pago al mismo tiempo
        results = []
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(attempt_purchase, token, order_id) for _ in range(50)]
            for f in futures:
                results.append(f.result())

        # Análisis de resultados
        successes = results.count(200)
        failures = results.count(400)
        others = len(results) - successes - failures

        print("\n--- RESULTADOS DEL STRESS TEST ---")
        print(f"Total de intentos simultáneos: {len(results)}")
        print(f"Pagos Exitosos (200 OK): {successes}")
        print(f"Pagos Rechazados (400 Bad Request): {failures}")
        print(f"Otros errores: {others}")

        if successes == 1:
            print("\n✅ RESULTADO: ÉXITO TOTAL. Solo una petición logró comprar el ticket.")
            print("El bloqueo atómico funciona perfectamente.")
        elif successes > 1:
            print("\n❌ RESULTADO: FALLO. Se vendió el ticket más veces de las permitidas.")
        else:
            print("\n⚠️ RESULTADO: Ningún pago tuvo éxito. Verifica que el sector tenga stock.")

    except Exception as e:
        print(f"Error durante la prueba: {e}")

if __name__ == "__main__":
    run_stress_test()
