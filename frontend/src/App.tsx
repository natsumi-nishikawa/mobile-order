import { useState } from 'react'

type Product = {
  id: number
  name: string
  price: number
  description: string | null
  image_url: string | null
  is_sold_out: boolean
  display_order: number | null
  category_ids: number[]
}

function App() {
  const [nickname, setNickname] = useState('')
  const [participantId, setParticipantId] = useState<number | null>(null)
  const [products, setProducts] = useState<Product[]>([])

  const handleStart = async () => {
    if (nickname.trim() === '') {
      alert('ニックネームを入力してください')
      return
    }

    try {
      // テーブル1の利用中Sessionを取得
      const sessionResponse = await fetch(
        'http://localhost:8000/api/customer/tables/1/session'
      )

      if (!sessionResponse.ok) {
        alert('現在利用できません')
        return
      }

      const session = await sessionResponse.json()

      // ニックネーム登録
      const participantResponse = await fetch(
        `http://localhost:8000/api/customer/sessions/${session.session_id}/participants`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            nickname: nickname.trim(),
          }),
        }
      )

      if (!participantResponse.ok) {
        const error = await participantResponse.json()
        alert(error.detail ?? 'ニックネームの登録に失敗しました')
        return
      }

      const participant = await participantResponse.json()

      // 商品一覧取得
      const productResponse = await fetch(
        'http://localhost:8000/api/customer/products'
      )

      if (!productResponse.ok) {
        alert('商品の取得に失敗しました')
        return
      }

      const productData = await productResponse.json()

      setParticipantId(participant.participant_id)
      setProducts(productData)

    } catch (error) {
      console.error(error)
      alert('通信に失敗しました')
    }
  }

  // 商品を1個選択
  const handleSelect = async (productId: number) => {
    if (participantId === null) {
      return
    }

    try {
      const response = await fetch(
        `http://localhost:8000/api/customer/selections/${productId}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            participant_id: participantId,
            quantity: 1,
          }),
        }
      )

      if (!response.ok) {
        const error = await response.json()
        alert(error.detail ?? '商品の選択に失敗しました')
        return
      }

      const selection = await response.json()

      console.log('選択結果:', selection)
      alert('商品を選択しました')

    } catch (error) {
      console.error(error)
      alert('通信に失敗しました')
    }
  }

  if (participantId !== null) {
    return (
      <div>
        <h1>メニュー</h1>

        <p>{nickname}さん</p>

        {products.length === 0 ? (
          <p>商品がありません</p>
        ) : (
          products.map((product) => (
            <div key={product.id}>
              <h2>{product.name}</h2>

              <p>¥{product.price}</p>

              {product.description && (
                <p>{product.description}</p>
              )}

              {product.is_sold_out ? (
                <p>売り切れ</p>
              ) : (
                <button onClick={() => handleSelect(product.id)}>
                  選択する
                </button>
              )}
            </div>
          ))
        )}
      </div>
    )
  }

  return (
    <div>
      <h1>モバイルオーダー</h1>

      <p>ニックネームを入力してください</p>

      <input
        type="text"
        value={nickname}
        onChange={(e) => setNickname(e.target.value)}
        maxLength={20}
        placeholder="例：たろう"
      />

      <button onClick={handleStart}>
        注文をはじめる
      </button>
    </div>
  )
}

export default App